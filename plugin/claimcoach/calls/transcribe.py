"""One transcription request to the local Voxtral server.

Implements: US-11.1 (``transcribe``: ``POST /v1/audio/transcriptions`` on ``mlx_audio.server``
with the recording and ``response_format=verbose_json``, which answers the model's output with
its token counts, so a transcript cut off at the length limit is flagged). Rules: BR-1 (loopback
only: the endpoint comes from ``ModelManager.use``; proxies are never honored), BR-14 (the
recording is sent under a fixed name, never the biller's filename; errors carry no model output).

``mlx_audio.server`` decodes the upload from its bytes, then writes it to a temporary file whose
suffix is the upload's: only some suffixes can be written, so every format is sent as
``call.wav`` (decoded M4A cannot be written back as M4A).
"""

from __future__ import annotations

from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from claimcoach.calls.types import AudioFormat
from claimcoach.cases.errors import TranscriptionFailedError, TranscriptionTimeoutError
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError

__all__ = ["MAX_TOKENS", "TRANSCRIBE_TIMEOUT", "Transcription", "transcribe"]

TRANSCRIBE_TIMEOUT: Final = 4 * 3600.0
"""Longest wait for the server's answer, in seconds; the scheduler sets a shorter one, ending
shortly after the window does."""
MAX_TOKENS: Final = 8192
"""Generation budget of the whole transcript (Voxtral generates it in one pass): about 30 minutes
of speech, which is also about as much audio as Voxtral transcribes at once."""
_UPLOAD_NAME: Final = "call.wav"
_MEDIA_TYPES: Final[dict[AudioFormat, str]] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
}


class _Reply(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    text: str
    generation_tokens: int = Field(default=0, ge=0)


class Transcription(BaseModel):
    """What the server transcribed.

    Attributes:
        text: The transcript, stripped.
        truncated: Generation stopped at ``MAX_TOKENS``, so the call's end is missing.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    truncated: bool


async def transcribe(
    endpoint: ModelEndpoint,
    audio: bytes,
    audio_format: AudioFormat,
    *,
    timeout: float = TRANSCRIBE_TIMEOUT,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Transcription:
    """Return the transcript of ``audio`` from the server at ``endpoint``.

    Args:
        endpoint: Loopback endpoint held through ``ModelManager.use``.
        audio: The recording.
        audio_format: Its format, from ``sniff_audio`` (its declared media type).
        timeout: Seconds to wait for each step of the request (connect, send, the answer).
        transport: Optional httpx transport for tests.

    Returns:
        The transcript and whether it was cut off.

    Raises:
        TranscriptionTimeoutError: The server did not answer within ``timeout``.
        ModelUnavailableError: The server did not answer, answered with an error, or answered
            with a body that is not a transcription.
        TranscriptionFailedError: The transcript is empty.
    """
    form = {
        # mlx_audio.server loads the model a request names, so it gets the server's own directory.
        "model": endpoint.model_path or DEFAULT_MODEL_ID,
        "response_format": "verbose_json",
        "language": "en",
        "max_tokens": str(MAX_TOKENS),
    }
    files = {"file": (_UPLOAD_NAME, audio, _MEDIA_TYPES[audio_format])}
    try:
        async with httpx.AsyncClient(
            timeout=timeout, transport=transport, trust_env=False
        ) as client:
            response = await client.post(
                f"{endpoint.base_url}/audio/transcriptions", data=form, files=files
            )
        response.raise_for_status()
        reply = _Reply.model_validate_json(response.content)
    except httpx.TimeoutException as exc:
        raise TranscriptionTimeoutError from exc
    except (httpx.HTTPError, ValidationError) as exc:
        raise ModelUnavailableError from exc
    text = reply.text.strip()
    if not text:
        raise TranscriptionFailedError
    return Transcription(text=text, truncated=reply.generation_tokens >= MAX_TOKENS)
