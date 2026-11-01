"""US-4.5 Retention Auto-Purge of Source Documents.

Scenarios: expired source documents are purged; a case inside the retention period is kept;
outcomes survive the purge de-identified; the retention period is configurable; a manual purge
needs confirmation. Also: the worker's scheduled purge, per-profile settings, failure isolation,
and the WAL truncation. Rules: BR-7, BR-14.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml
from pydantic import ValidationError

from claimcoach.corpus.crypto import InMemoryKeyProvider
from claimcoach.corpus.errors import CorpusError, CorpusKeyError
from claimcoach.corpus.paths import DATABASE, INDEX
from claimcoach.corpus.retention import RetentionJob, RetentionPolicy, purge_expired
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import CaseOutcome, PurgeRequest, PurgeResponse, utc_now
from claimcoach.settings import load_retention_days
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, add_case_document, corpus_client, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings

NOW = utc_now()
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> CorpusService:
    return make_service(tmp_path, corpus_server)


def set_retention(home: Path, days: object) -> None:
    home.mkdir(parents=True, exist_ok=True)
    config = {"plugins": {"entries": {"claimcoach": {"settings": {"retention_days": days}}}}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))


def counts(store: CorpusStore, case_id: str) -> tuple[int, int, int]:
    """Documents, chunks, and vectors of a case, counted in the raw files."""
    with sqlite3.connect(store.directory / DATABASE) as db:
        db.execute("ATTACH DATABASE ? AS idx", (str(store.directory / INDEX),))
        return (
            db.execute("SELECT count(*) FROM documents WHERE case_id = ?", (case_id,)).fetchone()[
                0
            ],
            db.execute("SELECT count(*) FROM chunks WHERE case_id = ?", (case_id,)).fetchone()[0],
            db.execute("SELECT count(*) FROM idx.vectors WHERE case_id = ?", (case_id,)).fetchone()[
                0
            ],
        )


# --- Scenario: Expired source documents are purged ----------------------------------------------


def test_us_4_5_expired_documents_purged(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "old", "Denied CO-50. " * 200, closed_days_ago=91, now=NOW)
    assert counts(store, "old")[0] == 1
    assert counts(store, "old")[1] > 1
    response = service.purge_all(NOW)
    [report] = response.reports
    assert (report.profile, report.cases, report.documents) == ("default", ["old"], 1)
    assert report.chunks == report.vectors > 1
    # No deleted page image stays in either WAL.
    for name in (DATABASE, INDEX):
        assert (store.directory / f"{name}-wal").stat().st_size == 0
    assert counts(store, "old") == (0, 0, 0)
    assert store.documents("old") == []
    assert store.open_case("old").purged_at == NOW
    assert service.purge_all(NOW).reports[0].cases == []  # re-running is a no-op


# --- Scenario: A case inside the retention period is kept ---------------------------------------


def test_us_4_5_case_inside_retention_kept(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "recent", "Denied CO-97.", closed_days_ago=89, now=NOW)
    add_case_document(store, "open", "Denied CO-16.", now=NOW)
    assert service.purge_all(NOW).reports[0].cases == []
    assert counts(store, "recent") == (1, 1, 1)
    assert counts(store, "open") == (1, 1, 1)


# --- Scenario: Outcomes survive the purge de-identified -----------------------------------------


def test_us_4_5_outcomes_survive_deidentified(service: CorpusService) -> None:
    document = PHI_DOCUMENTS[2]
    store = service.user_store("default", create=True)
    add_case_document(store, "won", document["text"], closed_days_ago=120, now=NOW)
    store.record_outcome("won", CaseOutcome.OVERTURNED, at=NOW - timedelta(days=121))
    service.purge_all(NOW)
    outcome = store.outcome("won")
    assert outcome is not None
    assert outcome.outcome is CaseOutcome.OVERTURNED
    assert leaked_strings(outcome.model_dump_json(), document) == []
    with sqlite3.connect(store.directory / DATABASE) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(outcomes)")]
    # Nothing free-text to leak; ``features`` is the de-identified snapshot of US-8.2.
    assert columns == ["case_id", "outcome", "recorded_at", "features"]


# --- Scenario: Retention period is configurable -------------------------------------------------


def test_us_4_5_retention_configurable(tmp_path: Path, service: CorpusService) -> None:
    set_retention(tmp_path, 30)
    set_retention(tmp_path / "profiles" / "b", 365)
    default, other = (
        service.user_store("default", create=True),
        service.user_store("b", create=True),
    )
    add_case_document(default, "c31", "Denied CO-18.", closed_days_ago=31, now=NOW)
    add_case_document(default, "c29", "Denied CO-18.", closed_days_ago=29, now=NOW)
    add_case_document(other, "c200", "Denied CO-18.", closed_days_ago=200, now=NOW)
    reports = {r.profile: r.cases for r in service.purge_all(NOW).reports}
    assert reports == {"default": ["c31"], "b": []}
    assert counts(default, "c31") == (0, 0, 0)
    assert counts(default, "c29") == (1, 1, 1)
    assert counts(other, "c200") == (1, 1, 1)


@pytest.mark.parametrize("days", [0, "thirty", None, 5000])
def test_us_4_5_untrusted_retention_skips_the_profile(
    tmp_path: Path, service: CorpusService, days: object
) -> None:
    """An invalid retention setting never shortens retention: the profile is skipped this run."""
    set_retention(tmp_path, days)
    store = service.user_store("default", create=True)
    add_case_document(store, "c91", "Denied CO-18.", closed_days_ago=91, now=NOW)
    response = service.purge_all(NOW)
    assert (response.reports, response.skipped) == ([], ["default"])
    assert counts(store, "c91") == (1, 1, 1)
    named = service.purge(PurgeRequest(profile="default"), NOW)
    assert (named.reports, named.skipped) == ([], ["default"])


def test_us_4_5_unrelated_invalid_setting_keeps_retention(
    tmp_path: Path, service: CorpusService
) -> None:
    """``retention_days`` is validated on its own: a bad sibling setting cannot reset it to 90."""
    config = {
        "plugins": {
            "entries": {
                "claimcoach": {
                    "settings": {"retention_days": 365, "richer_agent_access": "yes", "x": 1}
                }
            }
        }
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))
    store = service.user_store("default", create=True)
    add_case_document(store, "c200", "Denied CO-18.", closed_days_ago=200, now=NOW)
    assert service.purge_all(NOW).reports[0].cases == []
    assert counts(store, "c200") == (1, 1, 1)


def test_us_4_5_profile_settings_read(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert load_retention_days(tmp_path / "nowhere") == 90
    set_retention(tmp_path, 45)
    assert load_retention_days(tmp_path) == 45
    assert RetentionPolicy.for_profile(tmp_path) == RetentionPolicy(days=45)
    (tmp_path / "config.yaml").write_text("plugins: [unclosed")
    with caplog.at_level(logging.WARNING):
        assert load_retention_days(tmp_path) is None
        assert RetentionPolicy.for_profile(tmp_path) is None
    assert "retention purge is skipped" in caplog.text
    (tmp_path / "config.yaml").write_bytes(b"\xff\xfe")
    assert load_retention_days(tmp_path) is None
    (tmp_path / "config.yaml").write_text("plugins: {}")
    assert load_retention_days(tmp_path) == 90


# --- Scenario: Manual purge without confirmation ------------------------------------------------


async def test_us_4_5_manual_purge_requires_confirm(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "open-case", "Denied CO-4.", now=NOW)
    with pytest.raises(ValidationError):
        PurgeRequest(profile="default", case_id="open-case")
    with pytest.raises(ValidationError):
        PurgeRequest(case_id="open-case", confirm=True)  # names no profile
    with corpus_client(service) as (client, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://w") as http:
            refused = await http.post(
                "/corpus/purge", json={"profile": "default", "case_id": "open-case"}, headers=AUTH
            )
            missing = await http.post(
                "/corpus/purge",
                json={"profile": "default", "case_id": "nope", "confirm": True},
                headers=AUTH,
            )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "invalid_request"
        assert counts(store, "open-case") == (1, 1, 1)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "case_not_found"
        done = await client.purge_corpus(
            PurgeRequest(profile="default", case_id="open-case", confirm=True)
        )
        profile_only = await client.purge_corpus(PurgeRequest(profile="default"))
    assert done.reports[0].cases == ["open-case"]
    assert profile_only.reports[0].cases == []
    assert counts(store, "open-case") == (0, 0, 0)


# --- The worker's scheduled purge ---------------------------------------------------------------


async def test_us_4_5_worker_runs_scheduled_purge(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "old", "Denied CO-50.", closed_days_ago=100)
    app = create_app(TOKEN, corpus=service)
    async with app.router.lifespan_context(app):
        for _ in range(200):
            if counts(store, "old") == (0, 0, 0):
                break
            await asyncio.sleep(0.01)
        assert counts(store, "old") == (0, 0, 0)
    with pytest.raises(sqlite3.ProgrammingError):  # the lifespan closed the stores
        store.status()


async def test_us_4_5_retention_job_survives_failures(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[int] = []

    def purge_all() -> PurgeResponse:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("disk I/O error")
        return PurgeResponse(reports=[])

    task = asyncio.create_task(RetentionJob(purge_all, interval=0.01).run())
    with caplog.at_level(logging.INFO):
        while len(calls) < 3:
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "retention purge failed: OperationalError" in caplog.text
    assert "removed the content of 0 cases" in caplog.text
    assert "disk I/O" not in caplog.text


class _FailFor(InMemoryKeyProvider):
    def __init__(self, account: str) -> None:
        super().__init__()
        self.account = account

    def key_for(self, account: str, *, create: bool) -> bytes:
        if account == self.account:
            raise CorpusKeyError
        return super().key_for(account, create=create)


def test_us_4_5_failing_profile_does_not_stop_others(
    tmp_path: Path, corpus_server: FakeModelServer, caplog: pytest.LogCaptureFixture
) -> None:
    setup = make_service(tmp_path, corpus_server)
    keys = setup._keys
    add_case_document(setup.user_store("default", create=True), "c", "Denied.", closed_days_ago=100)
    add_case_document(setup.user_store("locked", create=True), "c", "Denied.", closed_days_ago=100)
    setup.close()
    failing = _FailFor("user-store:locked")
    failing.keys = keys.keys  # type: ignore[attr-defined]
    service = make_service(tmp_path, corpus_server, keys=failing)
    with caplog.at_level(logging.ERROR):
        reports = service.purge_all(NOW).reports
    assert [(r.profile, r.cases) for r in reports] == [("default", ["c"])]
    assert "retention purge skipped a profile: CorpusKeyError" in caplog.text


def test_us_4_5_purge_needs_user_scope(service: CorpusService) -> None:
    with pytest.raises(CorpusError):
        purge_expired(service.global_store(), RetentionPolicy())


# --- Review regressions -------------------------------------------------------------------------


def test_us_4_5_close_times_compare_in_utc(service: CorpusService) -> None:
    """A close time with a local offset is stored in UTC, so text order is time order."""
    store = service.user_store("default", create=True)
    cutoff = datetime(2026, 7, 1, 23, 0, tzinfo=UTC)
    local = timezone(timedelta(hours=-5))
    # 20:00-05:00 is 01:00 UTC the next day: after the cutoff, so not expired.
    add_case_document(store, "late", "Denied.", now=NOW)
    store.close_case("late", at=datetime(2026, 7, 1, 20, 0, tzinfo=local))
    assert store.expired_cases(cutoff) == []
    assert store.expired_cases(cutoff + timedelta(hours=3)) == ["late"]


def test_us_4_5_closing_again_keeps_the_retention_clock(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "c", "Denied.", closed_days_ago=100, now=NOW)
    first = store.open_case("c").closed_at
    store.close_case("c", at=NOW)
    assert store.open_case("c").closed_at == first


def test_us_4_5_blocked_checkpoint_is_reported(
    service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    store = service.user_store("default", create=True)
    add_case_document(store, "c", "Denied.", closed_days_ago=100, now=NOW)
    reader = sqlite3.connect(store.directory / DATABASE, isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM documents").fetchone()
        add_case_document(store, "d", "Denied again.", now=NOW)  # WAL frames the reader pins
        with caplog.at_level(logging.WARNING):
            assert store.checkpoint() is False
    finally:
        reader.close()
    assert "checkpoint was blocked" in caplog.text
    assert store.checkpoint() is True


def test_us_4_5_storage_error_in_one_profile_does_not_stop_others(
    service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    good, bad = service.user_store("default", create=True), service.user_store("b", create=True)
    add_case_document(good, "c", "Denied.", closed_days_ago=100, now=NOW)
    add_case_document(bad, "c", "Denied.", closed_days_ago=100, now=NOW)

    def broken(_cutoff: datetime) -> list[str]:
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(bad, "expired_cases", broken)
    response = service.purge_all(NOW)
    assert [(r.profile, r.cases) for r in response.reports] == [("default", ["c"])]
    assert response.skipped == ["b"]


async def test_us_4_5_purge_runs_off_the_event_loop() -> None:
    """A slow purge (a Keychain prompt, a long secure-delete) never stalls the worker's loop."""
    release = threading.Event()
    started = threading.Event()

    def slow_purge() -> PurgeResponse:
        started.set()
        release.wait(5)
        return PurgeResponse(reports=[])

    task = asyncio.create_task(RetentionJob(slow_purge, interval=3600).run())
    try:
        while not started.is_set():
            await asyncio.sleep(0.005)
        ticks = 0
        for _ in range(5):  # the loop keeps running while the purge is blocked
            await asyncio.sleep(0.001)
            ticks += 1
        assert ticks == 5
        assert not release.is_set()
    finally:
        release.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
