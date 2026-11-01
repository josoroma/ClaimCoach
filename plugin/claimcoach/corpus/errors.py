"""Corpus errors and the envelope codes the worker answers them with.

Implements: US-4.1 (``IndexStaleError``, ``CaseNotFoundError``, ``ProfileNotFoundError``), US-4.2
(``CorpusKeyError``), US-5.1 (``CaseClosedError``), US-9.1 (``CodeNotFoundError``,
``PayerNotFoundError``).
Rules: ES-8 (each error maps to one fixed envelope code), BR-14 (no error carries document text,
key material, or tool output).
"""

from __future__ import annotations

from typing import ClassVar

from claimcoach.api.models import ErrorCode

__all__ = [
    "CaseClosedError",
    "CaseNotFoundError",
    "CodeNotFoundError",
    "CorpusError",
    "CorpusKeyError",
    "IndexStaleError",
    "PayerNotFoundError",
    "ProfileNotFoundError",
]


class CorpusError(Exception):
    """A corpus operation failed; ``code`` and ``status_code`` say how the worker answers."""

    code: ClassVar[ErrorCode] = "corpus_unavailable"
    status_code: ClassVar[int] = 503


class CorpusKeyError(CorpusError):
    """The user-store key is missing, unreadable, or does not decrypt the store."""


class IndexStaleError(CorpusError):
    """The vector index was built with another embedding model or dimension; reindex first."""

    code: ClassVar[ErrorCode] = "index_stale"
    status_code: ClassVar[int] = 409


class CaseNotFoundError(CorpusError):
    """No case with that ID in this user scope."""

    code: ClassVar[ErrorCode] = "case_not_found"
    status_code: ClassVar[int] = 404


class ProfileNotFoundError(CorpusError):
    """No user scope exists for that profile; reads never create one."""

    code: ClassVar[ErrorCode] = "profile_not_found"
    status_code: ClassVar[int] = 404


class CaseClosedError(CorpusError):
    """The case is closed or purged, so its content can no longer change (US-5.1)."""

    code: ClassVar[ErrorCode] = "case_closed"
    status_code: ClassVar[int] = 409


class CodeNotFoundError(CorpusError):
    """The global corpus has no entry for the asked code (US-9.1)."""

    code: ClassVar[ErrorCode] = "code_not_found"
    status_code: ClassVar[int] = 404


class PayerNotFoundError(CorpusError):
    """No global rule card names the asked payer (US-9.1)."""

    code: ClassVar[ErrorCode] = "payer_not_found"
    status_code: ClassVar[int] = 404
