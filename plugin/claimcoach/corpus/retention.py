"""Retention: purge case content a configurable period after the case closes.

Implements: US-4.5 (``RetentionPolicy`` from the profile's ``retention_days`` setting,
``purge_expired``, ``purge_case``, and ``RetentionJob``, the worker's scheduled purge). Rules:
BR-7 (default 90 days after close; outcomes kept de-identified), BR-14 (logs carry counts and
error types only).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import PurgeReport, PurgeResponse, utc_now
from claimcoach.logs import get_logger, job_context, new_request_id
from claimcoach.settings import load_retention_days

__all__ = ["PURGE_INTERVAL", "RetentionJob", "RetentionPolicy", "purge_case", "purge_expired"]

PURGE_INTERVAL: Final = 6 * 3600.0
"""Seconds between scheduled purges; the first runs when the worker starts."""

_log = get_logger("claimcoach.corpus")


class RetentionPolicy(BaseModel):
    """How long case content is kept after the case closes.

    Attributes:
        days: Days after close; the ``retention_days`` setting (default 90).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    days: int = Field(default=90, ge=1, le=3650)

    @classmethod
    def for_profile(cls, home: Path) -> RetentionPolicy | None:
        """Return the policy a profile's Hermes config sets, or ``None`` when it cannot be read.

        ``None`` means "skip this profile this run": an unreadable config must never shorten a
        retention period the practice chose (``load_retention_days`` fails closed).
        """
        days = load_retention_days(home)
        return None if days is None else cls(days=days)

    def cutoff(self, now: datetime) -> datetime:
        """Return the latest close time whose content is due for purge at ``now``."""
        return now - timedelta(days=self.days)


def _purge(
    store: CorpusStore, case_ids: list[str], now: datetime, reason: Literal["retention", "request"]
) -> PurgeReport:
    if store.profile is None:
        raise CorpusError("only a user scope holds case content")
    documents = chunks = vectors = 0
    for case_id in case_ids:
        counts = store.purge_case_content(case_id, at=now, reason=reason)
        documents, chunks, vectors = (
            documents + counts[0],
            chunks + counts[1],
            vectors + counts[2],
        )
    return PurgeReport(
        profile=store.profile,
        cases=case_ids,
        documents=documents,
        chunks=chunks,
        vectors=vectors,
    )


def purge_expired(
    store: CorpusStore, policy: RetentionPolicy, now: datetime | None = None
) -> PurgeReport:
    """Purge every case of ``store`` closed more than ``policy.days`` before ``now``.

    Args:
        store: A user scope.
        policy: Its retention policy.
        now: The time to judge against; the current time by default.

    Returns:
        What was removed. Re-running is a no-op.
    """
    when = now or utc_now()
    return _purge(store, store.expired_cases(policy.cutoff(when)), when, "retention")


def purge_case(store: CorpusStore, case_id: str, now: datetime | None = None) -> PurgeReport:
    """Purge one case now, whatever its retention date (manual purge, phi-purge runbook).

    Raises:
        CaseNotFoundError: No such case.
    """
    return _purge(store, [case_id], now or utc_now(), "request")


class RetentionJob:
    """The worker's scheduled purge.

    Each run goes to a worker thread, so the event loop (health checks, redaction, pane requests)
    never waits on the Keychain or on SQLite.

    Args:
        purge_all: Purges every profile's user scope (``CorpusService.purge_all``).
        interval: Seconds between runs.
    """

    def __init__(
        self, purge_all: Callable[[], PurgeResponse], *, interval: float = PURGE_INTERVAL
    ) -> None:
        """Store the purge callable; nothing runs until ``run``."""
        self._purge_all = purge_all
        self._interval = interval

    async def run(self) -> None:
        """Purge now, then every ``interval`` seconds, until cancelled."""
        while True:
            with job_context(f"purge-{new_request_id()}"):
                try:
                    response = await asyncio.to_thread(self._purge_all)
                except Exception as exc:  # noqa: BLE001 - the schedule must outlive one bad run
                    _log.error("retention purge failed: %s", type(exc).__name__)
                else:
                    purged = sum(len(report.cases) for report in response.reports)
                    _log.info("retention purge removed the content of %d cases", purged)
            await asyncio.sleep(self._interval)
