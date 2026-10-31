"""Structured JSON logs with request/job IDs, scrubbed of PHI before they are written.

Implements: US-3.4 (JSON formatter + redaction filter). Rules: ES-8 (logs are structured JSON with
request/job IDs and contain no document text), BR-14 (logs are redacted), PC-4.

Logging cannot call the PHI model (it is synchronous, may run inside the redactor itself, and
must never block), so a record is scrubbed with what is known without a model call:

- the regex validators (SSN, MRN, DOB, phone, member ID), and
- the process's ``PhiLedger``: every PHI value the redactor found in this process, so a name the
  model found in a document is also removed from any later log line that quotes it.

The primary rule stays that log calls pass codes, roles, ports, and type names — never document
text; the scrub is the safety net. Exception messages and tracebacks are dropped and only the
exception type is written, because messages routinely quote their input.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Final, TextIO

from claimcoach.redact.ledger import LEDGER, PhiLedger
from claimcoach.redact.spans import redact

__all__ = [
    "JsonFormatter",
    "PhiRedactionFilter",
    "configure_logging",
    "get_logger",
    "job_context",
    "job_id_var",
    "new_request_id",
    "request_id_var",
    "scrub",
]

request_id_var: ContextVar[str | None] = ContextVar("claimcoach_request_id", default=None)
"""ID of the HTTP request being served; set by the worker middleware."""

job_id_var: ContextVar[str | None] = ContextVar("claimcoach_job_id", default=None)
"""ID of the background job being run (idle sweep, download, conversion)."""

_process_job_id = f"process-{os.getpid()}"
"""Job ID of log lines outside any request or job: the process itself (startup, shutdown)."""


def scrub(text: str, ledger: PhiLedger = LEDGER) -> str:
    """Return ``text`` with known PHI values and regex-shaped PHI replaced by placeholders."""
    return redact(text, ledger.spans(text)).text


def _message(record: logging.LogRecord) -> str:
    """Return ``record.getMessage()`` scrubbed.

    A call whose arguments do not fit its format string (``getMessage`` raises) keeps only the
    scrubbed format string: the arguments are never written.
    """
    try:
        return scrub(record.getMessage())
    except Exception:  # noqa: BLE001 - a bad log call must neither crash the caller nor leak args
        return f"[unformattable log call] {scrub(str(record.msg))}"


def new_request_id() -> str:
    """Return a new random request ID (16 hex characters)."""
    return uuid.uuid4().hex[:16]


@contextmanager
def job_context(job_id: str) -> Iterator[None]:
    """Tag every log line written inside the block with ``job_id``."""
    token = job_id_var.set(job_id)
    try:
        yield
    finally:
        job_id_var.reset(token)


class PhiRedactionFilter(logging.Filter):
    """Scrub a record's message and drop its exception text before any handler sees it.

    Attached by ``get_logger`` to each ClaimCoach logger, so it also protects records that end up
    in handlers ClaimCoach does not own (the Hermes gateway's).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Rewrite ``record`` in place; never drops it."""
        record.msg = _message(record)
        record.args = None
        if record.exc_info and record.exc_info[0] is not None:
            record.claimcoach_exc_type = record.exc_info[0].__name__
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


_FILTER: Final = PhiRedactionFilter()


def get_logger(name: str) -> logging.Logger:
    """Return the logger ``name`` with the PHI filter attached (once)."""
    logger = logging.getLogger(name)
    if _FILTER not in logger.filters:
        logger.addFilter(_FILTER)
    return logger


class JsonFormatter(logging.Formatter):
    """One JSON object per line: time, level, logger, message, request or job ID, exception type.

    The message is scrubbed here as well, because records from other libraries (uvicorn) never
    pass through a ClaimCoach logger's filter.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Render ``record`` as a JSON line."""
        exc_type = getattr(record, "claimcoach_exc_type", None)
        if exc_type is None and record.exc_info and record.exc_info[0] is not None:
            exc_type = record.exc_info[0].__name__
        request_id = request_id_var.get()
        line = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": _message(record),
            "request_id": request_id,
            "job_id": job_id_var.get() or (None if request_id else _process_job_id),
        }
        if exc_type:
            line["exc_type"] = exc_type
        return json.dumps(line, ensure_ascii=False)


class _JsonStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """A stream handler whose own errors are one JSON line with the error type only.

    ``logging.Handler.handleError`` would print a traceback and the record's raw arguments.
    """

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 - logging's name
        """Write ``{"level": "error", "message": "logging failed", "exc_type": ...}``."""
        exc_type = sys.exc_info()[0]
        line = {
            "level": "error",
            "logger": record.name,
            "message": "logging failed",
            "request_id": request_id_var.get(),
            "job_id": job_id_var.get() or _process_job_id,
            "exc_type": exc_type.__name__ if exc_type else None,
        }
        with contextlib.suppress(Exception):  # nothing left to report to
            self.stream.write(json.dumps(line) + self.terminator)


def _log_uncaught(exc_type: type[BaseException], thread: str | None = None) -> None:
    get_logger("claimcoach.uncaught").error(
        "uncaught %s%s", exc_type.__name__, f" in thread {thread}" if thread else ""
    )


def configure_logging(
    process: str, stream: TextIO | None = None, level: int = logging.INFO
) -> logging.Handler:
    """Send every log record of this process to ``stream`` as JSON lines.

    Replaces the root logger's handlers and the uncaught-exception hooks (``sys.excepthook``,
    ``threading.excepthook``), so even a crash writes one JSON line with the exception type only.
    Run uvicorn with ``log_config=None`` so it keeps the handler.

    Args:
        process: Short process name, used in the process-level job ID (``worker-<pid>``).
        stream: Destination; defaults to ``sys.stderr`` (the worker's ``worker.log``).
        level: Root level.

    Returns:
        The installed handler.
    """
    global _process_job_id  # noqa: PLW0603 - one process, one ID, set once at startup
    _process_job_id = f"{process}-{os.getpid()}"
    handler = _JsonStreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)
    logging.captureWarnings(capture=True)
    # Uncaught exceptions would print a traceback (and their message) to worker.log.
    sys.excepthook = lambda exc_type, _exc, _tb: _log_uncaught(exc_type)
    threading.excepthook = lambda args: _log_uncaught(
        args.exc_type, args.thread.name if args.thread else None
    )
    return handler
