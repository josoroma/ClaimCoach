"""Per-launch bearer token for the worker.

Implements: US-1.2 (new token on every start, ``secrets.token_urlsafe``, file mode 0600).
Rules: PRD §7.9 worker decision (only ClaimCoach can call the worker).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Final

__all__ = ["TOKEN_BYTES", "issue_token", "read_token"]

TOKEN_BYTES: Final = 32
"""Entropy of the token in bytes (256 bits)."""


def issue_token(path: Path) -> str:
    """Generate a new token and store it at ``path`` with mode 0600.

    The token is written to a temporary file created with mode 0600 and then renamed over
    ``path``, so a reader never sees a partial token and the file is never wider than 0600.

    Args:
        path: Token file path; its parent is created with mode 0700.

    Returns:
        The new token.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token)
    tmp.replace(path)
    return token


def read_token(path: Path) -> str | None:
    """Return the token stored at ``path``, or ``None`` when there is no readable token.

    A missing, unreadable, or corrupt file means no worker the caller can use, so it is reported
    the same way as "not started" and the proxy answers ``worker_unavailable``.
    """
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token or None
