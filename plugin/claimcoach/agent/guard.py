"""PHI guard for agent tool results: each handler redacts its own result; the hook re-redacts.

Implements: US-3.2 (``redact_tool_result()`` wraps every ``claimcoach_*`` handler; the
``transform_tool_result`` hook is registered as a second guard). Rules: BR-3 (handlers redact
before returning — the primary guard), PC-7 (``transform_tool_result`` is fail-open, so it is
defense-in-depth only), PC-8 (handlers return a JSON string), BR-14, BR-2 (the text goes to the
worker's ``/redact`` on loopback and its local PHI model, nowhere else).

Neither guard ever raises. When the handler's redaction fails for any reason the agent gets the
``redaction_failed`` envelope instead of the result; when the hook's fails, it leaves the
(already redacted) handler result alone. A handler that raises yields the ``internal_error``
envelope, so Hermes never puts exception text (which could quote case content) into the
transcript or its logs.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable, Iterator, Mapping
from functools import wraps
from typing import Any, Final, Protocol

from pydantic import ValidationError

from claimcoach import PLUGIN_NAME
from claimcoach.api.client import WorkerClient
from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope, envelope
from claimcoach.logs import get_logger
from claimcoach.paths import app_data_dir
from claimcoach.redact.types import MAX_TEXT_CHARS, RedactRequest
from claimcoach.worker.config import WorkerConfig
from claimcoach.worker.token import read_token

__all__ = [
    "GUARD_TIMEOUT",
    "HOOK_NAME",
    "HOOK_TIMEOUT",
    "TOOL_PREFIX",
    "HookRegistrar",
    "Scrubber",
    "guard_text",
    "make_hook",
    "redact_tool_result",
    "register_guard_hook",
    "worker_scrubber",
]

TOOL_PREFIX: Final = f"{PLUGIN_NAME}_"
HOOK_NAME: Final = "transform_tool_result"
GUARD_TIMEOUT: Final = 180.0
"""Seconds one handler redaction may take, including a cold start of the PHI model."""
JOIN_GRACE: Final = 1.0
"""Seconds past the deadline before a stuck redaction thread is abandoned."""
HOOK_TIMEOUT: Final = 25.0
"""Seconds the hook's redaction may take: under Hermes' 30 s ``hook_callback_timeout``."""

Scrubber = Callable[[str], Awaitable[str]]
"""Returns the redacted text, or raises ``WorkerError`` when redaction could not run."""

_log = get_logger("claimcoach.agent")


class HookRegistrar(Protocol):
    """The slice of Hermes' ``PluginContext`` that hook registration uses."""

    def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> object:  # noqa: D102
        ...


def worker_scrubber(timeout: float = GUARD_TIMEOUT) -> Scrubber:
    """Return a scrubber that calls the worker's ``POST /redact``.

    Args:
        timeout: Seconds for the call.

    Returns:
        The scrubber; it resolves the worker's token on every call.
    """

    async def scrub(text: str) -> str:
        config = WorkerConfig(data_dir=app_data_dir())
        client = WorkerClient(
            config.base_url, lambda: read_token(config.token_path), timeout=timeout
        )
        return (await client.redact(RedactRequest(text=text))).text

    return scrub


def _run_blocking(scrubber: Scrubber, text: str, timeout: float) -> str:
    """Run ``scrubber`` to completion from sync code, whether or not a loop is running here.

    Hermes calls sync handlers and hooks from threads that may already run an event loop, so the
    coroutine gets its own daemon thread and loop, bounded by ``timeout`` in total. A timed-out
    call is abandoned (its thread is a daemon, so it never holds up gateway shutdown).

    Raises:
        TimeoutError: The call did not finish within ``timeout``.
        Exception: Whatever the scrubber raised.
    """
    outcome: list[str] = []
    failure: list[Exception] = []

    def run() -> None:
        try:
            outcome.append(asyncio.run(asyncio.wait_for(scrubber(text), timeout)))
        except Exception as exc:  # noqa: BLE001 - handed to the caller below
            failure.append(exc)

    thread = threading.Thread(target=run, name="claimcoach-redact", daemon=True)
    thread.start()
    # The coroutine's own deadline normally ends it first; the grace covers a scrubber that
    # blocks without awaiting, which no deadline inside the loop can interrupt.
    thread.join(timeout + JOIN_GRACE)
    if failure:
        raise failure[0]
    if not outcome:
        raise TimeoutError
    return outcome[0]


def _canonical_envelope(result: str) -> str | None:
    """Return ``result`` re-serialized if it is one of ClaimCoach's fixed error envelopes.

    Envelopes carry a code and that code's fixed message only, so they need no model call; the
    re-serialized form is returned, never the input string.
    """
    try:
        parsed = ErrorEnvelope.model_validate_json(result)
    except ValidationError:
        return None
    if parsed.error.message != ERROR_MESSAGES[parsed.error.code]:
        return None
    return envelope(parsed.error.code).model_dump_json()


_FIELD_SEP: Final = "\n\x1e\n"
"""Joins a JSON result's fields into one redaction call; never a word, never PHI."""

JsonValue = Any
"""A value produced by ``json.loads``."""


class _FieldsChangedError(Exception):
    """Redaction did not map the result's fields one to one (lost or merged a field or key)."""


def _is_number(node: JsonValue) -> bool:
    return isinstance(node, int | float) and not isinstance(node, bool)


def _fields(node: JsonValue) -> Iterator[str]:
    """Every key, string, and number of a decoded JSON document, depth first.

    Numbers are included because a careless handler may return an MRN or SSN as a number.
    """
    if isinstance(node, str):
        yield node
    elif _is_number(node):
        yield json.dumps(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _fields(value)
    elif isinstance(node, list):
        for item in node:
            yield from _fields(item)


def _rebuild(node: JsonValue, redacted: Iterator[str]) -> JsonValue:
    """``node`` with its fields replaced, in ``_fields`` order.

    A number whose redacted text is unchanged stays a number; otherwise it becomes the redacted
    string. Two keys that redact to the same text fail, rather than silently dropping one.
    """
    if isinstance(node, str):
        return next(redacted)
    if _is_number(node):
        text = next(redacted)
        return node if text == json.dumps(node) else text
    if isinstance(node, dict):
        rebuilt = {next(redacted): _rebuild(value, redacted) for value in node.values()}
        if len(rebuilt) != len(node):
            raise _FieldsChangedError
        return rebuilt
    if isinstance(node, list):
        return [_rebuild(item, redacted) for item in node]
    return node


def _redact(result: str, scrubber: Scrubber, timeout: float) -> str:
    """Redact ``result``; raises on any failure (callers decide how to fail)."""
    known = _canonical_envelope(result)
    if known is not None:
        return known
    try:
        document: JsonValue = json.loads(result)
    except ValueError:
        return _redact_fields([result], scrubber, timeout)[0]
    fields = list(_fields(document))
    if not fields:
        return result  # null, true, false, [] or {}: nothing that could be PHI
    redacted = iter(_redact_fields(fields, scrubber, timeout))
    return json.dumps(_rebuild(document, redacted))


def _redact_fields(fields: list[str], scrubber: Scrubber, timeout: float) -> list[str]:
    joined = _FIELD_SEP.join(fields)
    if len(joined) > MAX_TEXT_CHARS:
        raise _FieldsChangedError  # too large for one /redact call: fail closed, never truncate
    redacted = _run_blocking(scrubber, joined, timeout).split(_FIELD_SEP)
    if len(redacted) != len(fields):
        raise _FieldsChangedError
    return redacted


def guard_text(
    result: str,
    scrubber: Scrubber,
    timeout: float = GUARD_TIMEOUT,
    fallback: str | None = None,
) -> str | None:
    """Return ``result`` redacted, or ``fallback`` when redaction fails for any reason.

    A JSON result is redacted field by field: its keys, strings, and numbers are decoded first, so
    a JSON escape (an escaped newline before a name) cannot hide a value from the word boundaries
    of the redactor, and the redacted document is serialized again. Other text is redacted as is.

    Nothing raises out of here: an exception would reach Hermes, which quotes exception text to
    the agent and its logs, and validation errors quote their input (BR-14).

    Args:
        result: A tool result string.
        scrubber: Redaction call.
        timeout: Seconds before giving up.
        fallback: What to return when redaction fails; the handler passes the
            ``redaction_failed`` envelope, the hook passes ``None`` (keep the handler's result).

    Returns:
        A PHI-free string, or ``fallback``.
    """
    try:
        return _redact(result, scrubber, timeout)
    except Exception as exc:  # noqa: BLE001 - any failure fails closed; only the type is logged
        _log.warning("tool result redaction failed: %s", type(exc).__name__)
        return fallback


Handler = Callable[..., str]


def redact_tool_result(
    handler: Callable[..., object],
    *,
    scrubber: Scrubber | None = None,
    timeout: float = GUARD_TIMEOUT,
) -> Handler:
    """Wrap a tool handler so its result is redacted before Hermes sees it (BR-3).

    Args:
        handler: ``handler(args, **context) -> str`` as Hermes calls it (a non-string result is
            treated as a handler bug).
        scrubber: Redaction call; defaults to the worker's ``/redact``.
        timeout: Seconds a redaction may take.

    Returns:
        The guarded handler; it never raises and never returns unredacted text.
    """
    scrub = scrubber or worker_scrubber(timeout)
    failed = envelope("redaction_failed").model_dump_json()

    @wraps(handler)
    def guarded(args: Mapping[str, Any], **context: Any) -> str:  # noqa: ANN401
        try:
            result = handler(args, **context)
        except Exception as exc:  # noqa: BLE001 - Hermes would quote the exception to the agent
            _log.error("tool handler failed: %s", type(exc).__name__)
            return envelope("internal_error").model_dump_json()
        if not isinstance(result, str):
            _log.error("tool handler returned %s, not a JSON string", type(result).__name__)
            return envelope("internal_error").model_dump_json()
        return guard_text(result, scrub, timeout, fallback=failed) or failed

    guarded.__claimcoach_guarded__ = True  # type: ignore[attr-defined]
    return guarded


def make_hook(
    scrubber: Scrubber | None = None, timeout: float = HOOK_TIMEOUT
) -> Callable[..., str | None]:
    """Build the ``transform_tool_result`` callback (PC-7: defense in depth only).

    The hook re-redacts what the handler already redacted. When its own redaction fails it
    returns ``None``, so Hermes keeps the handler-redacted result. Its timeout stays under
    Hermes' ``plugins.hook_callback_timeout`` (30 s), past which Hermes drops the callback and
    skips it for a while.

    Args:
        scrubber: Redaction call; defaults to the worker's ``/redact``.
        timeout: Seconds a redaction may take.

    Returns:
        A callback that re-redacts ``claimcoach_*`` results and leaves other tools' results
        alone (``None``).
    """
    scrub = scrubber or worker_scrubber(timeout)

    def transform_tool_result(tool_name: str, result: object, **_payload: Any) -> str | None:  # noqa: ANN401
        if not tool_name.startswith(TOOL_PREFIX) or not isinstance(result, str):
            return None
        return guard_text(result, scrub, timeout)

    return transform_tool_result


def register_guard_hook(ctx: HookRegistrar, scrubber: Scrubber | None = None) -> None:
    """Register the second guard with Hermes.

    Args:
        ctx: Hermes plugin context.
        scrubber: Redaction call; defaults to the worker's ``/redact``.
    """
    ctx.register_hook(HOOK_NAME, make_hook(scrubber))
