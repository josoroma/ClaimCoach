"""OpenAI-compatible chat completions against a local model server.

Implements: US-3.1 (the PHI detector's model call), US-5.2 (page images for the extraction model
as OpenAI ``image_url`` parts with ``data:`` URLs; the extraction role names its served model).
Rules: BR-1 (loopback only: the endpoint comes from ``ModelManager.use``; proxies are never
honored), BR-10 (only a ``BuiltPrompt`` can be sent, so every prompt goes through the US-3.6
data-block encoder), BR-14 (errors carry no model output).
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from claimcoach.models.manager import ModelEndpoint, ModelUnavailableError
from claimcoach.models.types import ModelRole
from claimcoach.prompts.builder import BuiltPrompt

__all__ = ["DEFAULT_MODEL_ID", "ChatReply", "chat_completion"]

DEFAULT_MODEL_ID: Final = "default_model"
"""``mlx_lm.server`` serves the model it was started with under this id."""


class _Loose(BaseModel):
    # Server responses carry many optional fields; only the ones read here are declared.
    model_config = ConfigDict(extra="ignore", frozen=True)


class _Message(_Loose):
    content: str


class _Choice(_Loose):
    message: _Message
    finish_reason: str | None = None


class _Completion(_Loose):
    choices: list[_Choice]


class ChatReply(BaseModel):
    """The assistant's reply.

    Attributes:
        content: Reply text.
        truncated: The server stopped at ``max_tokens``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    truncated: bool


def _model_id(endpoint: ModelEndpoint) -> str:
    # mlx_lm.server answers to its default id; mlx_vlm.server (the extraction role) loads the
    # model a request names, so it is sent the directory its server was started with.
    if endpoint.role is ModelRole.EXTRACTION and endpoint.model_path:
        return endpoint.model_path
    return DEFAULT_MODEL_ID


def _messages(prompt: BuiltPrompt, images: Sequence[bytes]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [message.model_dump() for message in prompt.messages]
    if images:
        # The image parts follow the user message's text, which ends with its data blocks; the
        # system message's data rule covers them too (BR-10).
        user = messages[-1]
        user["content"] = [
            {"type": "text", "text": user["content"]},
            *(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64.b64encode(png).decode()}"},
                }
                for png in images
            ),
        ]
    return messages


async def chat_completion(  # noqa: PLR0913 - one request: endpoint, prompt, images, limits
    endpoint: ModelEndpoint,
    prompt: BuiltPrompt,
    *,
    max_tokens: int,
    images: Sequence[bytes] = (),
    timeout: float = 120.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ChatReply:
    """Send ``prompt`` to ``endpoint`` with temperature 0 and return the first choice.

    Args:
        endpoint: Loopback endpoint held through ``ModelManager.use``.
        prompt: Messages built by ``build_prompt``.
        max_tokens: Completion budget.
        images: PNG images appended to the user message (vision models only).
        timeout: Seconds for the whole request.
        transport: Optional httpx transport for tests.

    Returns:
        The reply.

    Raises:
        ModelUnavailableError: The server did not answer, answered with an error, or answered
            with a body that is not a chat completion.
    """
    body = {
        "model": _model_id(endpoint),
        "messages": _messages(prompt, images),
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout, transport=transport, trust_env=False
        ) as client:
            response = await client.post(f"{endpoint.base_url}/chat/completions", json=body)
        response.raise_for_status()
        completion = _Completion.model_validate_json(response.content)
        choice = completion.choices[0]
    except (httpx.HTTPError, ValidationError, IndexError) as exc:
        raise ModelUnavailableError from exc
    return ChatReply(content=choice.message.content, truncated=choice.finish_reason == "length")
