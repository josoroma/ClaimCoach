"""What a call recording is, decided from its leading bytes.

Implements: US-11.1 (``sniff_audio``: WAV, MP3, FLAC, or M4A, never from the filename or the
declared type; the formats ``mlx_audio`` decodes; ``read_call_body`` and ``parse_call_upload``
read a recording's upload with the call's own limit and refusals). Rules: ES-8 (a refusal is one
fixed ``CaseError``), BR-14 (errors carry no content).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Final

from claimcoach.calls.types import MAX_CALL_BODY, MAX_CALL_BYTES, AudioFormat
from claimcoach.cases.errors import (
    CallTooLargeError,
    DocumentTooLargeError,
    UnsupportedAudioError,
    UnsupportedDocumentError,
)
from claimcoach.cases.intake import UploadedFile, parse_upload, read_limited

__all__ = ["parse_call_upload", "read_call_body", "sniff_audio"]

_MP4_BRANDS: Final = frozenset({b"M4A ", b"M4B ", b"mp41", b"mp42", b"isom"})
"""``ftyp`` major brands of AAC audio in an MP4 container (Voice Memos, call recorders)."""


def _mpeg_audio_frame(data: bytes) -> bool:
    """An MPEG audio frame header: 11 sync bits, a valid version, and a layer (not ADTS AAC)."""
    if len(data) < 2 or data[0] != 0xFF or data[1] & 0xE0 != 0xE0:
        return False
    version, layer = data[1] & 0x18, data[1] & 0x06
    return version != 0x08 and layer != 0


def sniff_audio(data: bytes) -> AudioFormat:
    """Return the format of a recording from its leading bytes.

    Raises:
        UnsupportedAudioError: Not WAV, MP3, FLAC, or M4A audio.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[4:8] == b"ftyp" and data[8:12] in _MP4_BRANDS:
        return "m4a"
    if data[:3] == b"ID3" or _mpeg_audio_frame(data):
        return "mp3"
    raise UnsupportedAudioError


async def read_call_body(chunks: AsyncIterator[bytes], declared: str | None) -> bytes:
    """Read a recording upload's body of at most ``MAX_CALL_BODY`` bytes into memory.

    Raises:
        CallTooLargeError: The body is over the limit.
    """
    try:
        return await read_limited(chunks, MAX_CALL_BODY, declared)
    except DocumentTooLargeError as exc:
        raise CallTooLargeError from exc


def parse_call_upload(body: bytes, content_type: str) -> UploadedFile:
    """Return the one ``file`` part of a recording upload.

    Raises:
        MalformedUploadError: Not exactly one part named ``file``.
        CallTooLargeError: The recording is over ``MAX_CALL_BYTES``.
        UnsupportedAudioError: The recording is empty.
    """
    try:
        return parse_upload(body, content_type, MAX_CALL_BYTES)
    except DocumentTooLargeError as exc:
        raise CallTooLargeError from exc
    except UnsupportedDocumentError as exc:
        raise UnsupportedAudioError from exc
