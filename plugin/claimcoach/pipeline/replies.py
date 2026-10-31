"""Read the JSON object a local model answers with, and nothing else.

Implements: US-5.2 (the extraction reply; lists read one item at a time), US-6.1 (the
classification reply), US-6.2 (the explanation reply's checklist). Rules: BR-10 (a model reply is
data: only its JSON object is read, then validated by the caller's typed model), BR-14.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Final

from pydantic import TypeAdapter, ValidationError

__all__ = ["clip", "clipped", "each_valid", "reply_object"]

_THINK: Final = re.compile(r"<think>.*?</think>", re.DOTALL)


def reply_object(content: str) -> dict[str, Any] | None:
    """Return the JSON object in a model reply, or ``None`` when there is none.

    Tolerates a ``<think>`` block and code fences or prose around one object: the text from the
    first ``{`` to the last ``}`` must parse as JSON.
    """
    text = _THINK.sub("", content)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value: dict[str, Any] = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return value


def each_valid(adapter: TypeAdapter[Any]) -> Callable[[object], list[Any]]:
    """Read a list one item at a time: ``null`` or a non-list is empty, a bad item is dropped.

    For a ``BeforeValidator``: one malformed item in a model reply never loses the rest.
    """

    def read(value: object) -> list[Any]:
        if not isinstance(value, list):
            return []
        items = []
        for item in value:
            try:
                items.append(adapter.validate_python(item))
            except ValidationError:
                continue
        return items

    return read


def clip(text: str, limit: int) -> str:
    """Shorten ``text`` (stripped) to at most ``limit`` characters, ending with ``…`` when cut.

    A model's prose that runs long is shortened, not refused: at temperature 0 a retry would
    write the same text, so refusing it would refuse the case forever.
    """
    text = text.strip()
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def clipped(limit: int) -> Callable[[object], object]:
    """A ``BeforeValidator`` that clips text to ``limit``; any other value is left to validation."""

    def read(value: object) -> object:
        return clip(value, limit) if isinstance(value, str) else value

    return read
