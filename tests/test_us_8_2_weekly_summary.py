"""US-8.2 Opt-In De-identified Aggregation and Weekly Summary (Python half).

Scenarios: only opted-in profiles are aggregated; aggregation never reads raw documents. Also: the
opt-in setting, the de-identified snapshot taken with an outcome, the ISO week in this Mac's time
zone, the counts and overturn rate, the migration of older outcome tables, and the routes.
Rules: ES-1, ES-4, ES-8, BR-7, BR-14, PRD §9.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.diagnosis import AppealLikelihood, DenialReason, Diagnosis
from claimcoach.cases.extraction import CaseExtraction
from claimcoach.cases.service import CaseService
from claimcoach.corpus import store as store_module
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.paths import DATABASE, profile_home, profile_user_scope_dir
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import read_outcomes
from claimcoach.corpus.types import MAX_FEATURES_CHARS, CaseOutcome, OutcomeRow
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.outcomes import summary as summary_module
from claimcoach.outcomes.features import OutcomeFeatures, outcome_features
from claimcoach.outcomes.summary import build_weekly_summary, last_completed_week, week_bounds
from claimcoach.outcomes.types import CategoryRow, OutcomeCounts, WeeklySummary
from claimcoach.settings import ClaimCoachSettings, load_outcome_sharing
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, add_case_document, make_service
from tests.fakes.diagnosis import (
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope

NEW_YORK = ZoneInfo("America/New_York")
WEEK = "2026-W43"
"""Monday 2026-10-19 to Monday 2026-10-26."""
IN_WEEK = datetime(2026, 10, 21, 15, tzinfo=UTC)

ACME = OutcomeFeatures(
    payer="ACME Health", denial_reason=DenialReason.PRIOR_AUTHORIZATION, codes=["CO-197", "N286"]
)
OTHER = OutcomeFeatures(
    payer="Other Payer", denial_reason=DenialReason.TIMELY_FILING, codes=["CO-29"]
)


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    """Fake Qwen3-8B and Qwen3-14B, each answering its own role's prompt."""
    replies = {
        ModelRole.CLASSIFICATION: classification_reply(),
        ModelRole.EXPLANATION: explanation_reply(),
    }
    servers = {role: FakeModelServer(replies={DEFAULT_MODEL_ID: r}) for role, r in replies.items()}
    for server in servers.values():
        server.start()
    yield servers
    for server in servers.values():
        server.stop()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "hermes"


@pytest.fixture
def service(root: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(root, corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def models(role_servers: dict[ModelRole, FakeModelServer]) -> Any:
    return role_models({role: server.base_url for role, server in role_servers.items()})


def share(root: Path, profile: str, value: object = True) -> None:
    """Write ``share_outcome_stats`` into the profile's config, as Settings → Plugins does."""
    home = profile_home(profile, root)
    home.mkdir(parents=True, exist_ok=True)
    config = {"plugins": {"entries": {"claimcoach": {"settings": {"share_outcome_stats": value}}}}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))


def record(
    service: CorpusService,
    profile: str,
    case_id: str,
    outcome: CaseOutcome,
    features: OutcomeFeatures | None = ACME,
    *,
    at: datetime = IN_WEEK,
) -> None:
    store = service.user_store(profile, create=True)
    store.create_case(case_id, at=at - timedelta(days=30))
    snapshot = None if features is None else features.model_dump_json()
    store.record_outcome(case_id, outcome, features=snapshot, at=at)


def summarize(root: Path, week: str = WEEK) -> WeeklySummary:
    return build_weekly_summary(root, week, tz=NEW_YORK)


# --- Scenario: Only opted-in profiles are aggregated ---------------------------------------------


def test_us_8_2_only_opted_in_profiles(
    root: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    share(root, "default")  # profile A opted in; profile B never did
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    record(service, "default", "a2", CaseOutcome.UPHELD)
    record(service, "b", "b1", CaseOutcome.WRITTEN_OFF)
    record(service, "b", "b2", CaseOutcome.WRITTEN_OFF)
    opened: list[str] = []
    real_connect = sqlite3.connect

    def traced(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        opened.append(str(database))
        connection: sqlite3.Connection = real_connect(database, *args, **kwargs)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced)

    summary = summarize(root)

    b_scope = profile_user_scope_dir("b", root, create=False).as_uri()
    assert opened, "A was read"
    assert not [path for path in opened if path.startswith(b_scope)], "review: B is not opened"

    assert summary.profiles == ["default"]
    assert summary.not_shared == 1
    assert (summary.totals.overturned, summary.totals.upheld, summary.totals.written_off) == (
        1,
        1,
        0,
    ), "A's two outcomes, none of B's"
    assert summary.totals.total == 2


def test_us_8_2_revoking_excludes_the_profile(root: Path, service: CorpusService) -> None:
    share(root, "default")
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    assert summarize(root).totals.total == 1
    share(root, "default", False)
    revoked = summarize(root)
    assert (revoked.profiles, revoked.not_shared, revoked.totals.total) == ([], 1, 0)


@pytest.mark.parametrize(
    ("stored", "shared"),
    [(True, True), (False, False), ("yes", False), (1, False), (None, False)],
)
def test_us_8_2_sharing_needs_an_explicit_true(
    tmp_path: Path, stored: object, shared: bool
) -> None:
    share(tmp_path, "default", stored)
    assert load_outcome_sharing(tmp_path) is shared


def test_us_8_2_sharing_fails_closed(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert load_outcome_sharing(tmp_path) is False, "no config: off by default"
    assert ClaimCoachSettings().share_outcome_stats is False
    (tmp_path / "config.yaml").write_text("plugins: [unclosed")
    with caplog.at_level(logging.WARNING):
        assert load_outcome_sharing(tmp_path) is False
    assert "outcomes are not shared" in caplog.text
    stored: dict[str, object] = {"retention_days": "x"}
    config = {"plugins": {"entries": {"claimcoach": {"settings": stored}}}}
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))
    assert load_outcome_sharing(tmp_path) is False, "another invalid setting changes nothing"
    stored["share_outcome_stats"] = True
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))
    assert load_outcome_sharing(tmp_path) is True


# --- Scenario: Aggregation never reads raw documents ---------------------------------------------


def test_us_8_2_aggregation_reads_only_outcomes(
    root: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    share(root, "default")
    store = service.user_store("default", create=True)
    document = PHI_DOCUMENTS[0]
    add_case_document(store, "c1", document["text"], closed_days_ago=10)
    store.record_outcome("c1", CaseOutcome.UPHELD, features=ACME.model_dump_json(), at=IN_WEEK)
    statements: list[str] = []
    real_connect = sqlite3.connect

    def traced(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection: sqlite3.Connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    def no_store(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the summary opened a case store")

    monkeypatch.setattr(sqlite3, "connect", traced)  # the store module's sqlite3 is this one
    monkeypatch.setattr(store_module.CorpusStore, "__init__", no_store)

    summary = summarize(root)

    assert summary.totals.upheld == 1
    assert statements, "the outcomes were read"
    for statement in statements:
        assert "main.outcomes" in statement, statement
        for table in ("documents", "chunks", "case_items", "vectors", "meta", "audit_log"):
            assert f" {table}" not in statement, statement
    assert leaked_strings(summary.model_dump_json(), document) == []


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT body FROM main.documents",
        "SELECT payload FROM main.case_items",
        "SELECT body FROM main.chunks",
        "SELECT value FROM main.meta",
        "SELECT case_id FROM main.audit_log",
        "ATTACH DATABASE 'other.sqlite3' AS other",
        "PRAGMA table_info(documents)",
        "DELETE FROM main.outcomes",
    ],
)
def test_us_8_2_reader_can_open_nothing_else(service: CorpusService, statement: str) -> None:
    """The authorizer ``read_outcomes`` installs refuses everything but reading ``outcomes``."""
    store = service.user_store("default", create=True)
    add_case_document(store, "c1", PHI_DOCUMENTS[0]["text"])
    with sqlite3.connect(f"{(store.directory / DATABASE).as_uri()}?mode=ro", uri=True) as db:
        db.set_authorizer(store_module._outcomes_only)
        with pytest.raises(sqlite3.DatabaseError):
            db.execute(statement)
        assert db.execute("SELECT outcome FROM main.outcomes").fetchall() == []


def test_us_8_2_reader_needs_no_key(service: CorpusService) -> None:
    """Outcomes are de-identified and stored plain, so the manager's view needs no profile key."""
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    directory = service.user_store("default").directory
    service.close()  # no store open, no key in memory
    rows = read_outcomes(directory, IN_WEEK - timedelta(days=1), IN_WEEK + timedelta(days=1))
    assert rows == [
        OutcomeRow(
            outcome=CaseOutcome.OVERTURNED, recorded_at=IN_WEEK, features=ACME.model_dump_json()
        )
    ]
    assert (
        read_outcomes(directory, IN_WEEK + timedelta(seconds=1), IN_WEEK + timedelta(days=1)) == []
    )


def test_us_8_2_reader_errors_are_corpus_errors(tmp_path: Path) -> None:
    with pytest.raises(CorpusError):
        read_outcomes(tmp_path / "missing", IN_WEEK, IN_WEEK)
    (tmp_path / DATABASE).write_bytes(b"not a database")
    with pytest.raises(CorpusError):
        read_outcomes(tmp_path, IN_WEEK, IN_WEEK)


def test_us_8_2_an_unreadable_profile_is_named(
    root: Path, service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    share(root, "default")
    share(root, "b")
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    record(service, "b", "b1", CaseOutcome.UPHELD)
    service.close()
    (profile_user_scope_dir("b", root) / DATABASE).write_bytes(b"garbage")
    with caplog.at_level(logging.WARNING):
        summary = summarize(root)
    assert (summary.profiles, summary.unreadable, summary.totals.total) == (["default"], ["b"], 1)
    assert "CorpusError" in caplog.text


# --- The de-identified snapshot ------------------------------------------------------------------


async def test_us_8_2_outcome_takes_the_snapshot(service: CorpusService, models: Any) -> None:
    """The payer as its rule cards name it, the denial reason, and the codes; no case text."""
    from claimcoach.pipeline.diagnose import Diagnoser  # noqa: PLC0415
    from claimcoach.pipeline.extract import Extractor  # noqa: PLC0415

    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    await Extractor(cases, models).run("default", case_id, lambda _s, _p: None)
    await Diagnoser(cases, models).run("default", case_id, lambda _s, _p: None)

    cases.record_outcome("default", case_id, CaseOutcome.OVERTURNED)

    rows = read_outcomes(
        service.user_store("default").directory,
        datetime.now(UTC) - timedelta(hours=1),
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert len(rows) == 1
    assert rows[0].features is not None
    features = OutcomeFeatures.model_validate_json(rows[0].features)
    assert (features.payer, features.denial_reason, features.codes) == (
        "ACME Health",
        DenialReason.PRIOR_AUTHORIZATION,
        ["CO-197", "N286"],
    )  # US-8.3 adds the classifier's facts; amounts and codes only
    for case_text in ("ACME HEALTH PLAN", "CLAIM-77", "PCN-0001", "SYNTHETIC", "2026-09-01"):
        assert case_text not in rows[0].features


async def test_us_8_2_snapshot_of_a_case_without_a_current_diagnosis(
    service: CorpusService, models: Any
) -> None:
    from claimcoach.pipeline.extract import Extractor  # noqa: PLC0415

    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    await Extractor(cases, models).run("default", case_id, lambda _s, _p: None)
    store = service.user_store("default")
    extraction = cases.extraction(store, case_id)
    assert outcome_features(None, None) is None, "a purged case keeps its snapshot"
    assert outcome_features(extraction, None) == OutcomeFeatures()


def test_us_8_2_a_correction_after_the_purge_keeps_the_snapshot(service: CorpusService) -> None:
    record(service, "default", "c1", CaseOutcome.UPHELD)
    service.user_store("default").record_outcome("c1", CaseOutcome.OVERTURNED, at=IN_WEEK)
    (row,) = read_outcomes(
        service.user_store("default").directory, IN_WEEK, IN_WEEK + timedelta(seconds=1)
    )
    assert (row.outcome, row.features) == (CaseOutcome.OVERTURNED, ACME.model_dump_json())


def test_us_8_2_an_older_outcomes_table_gains_features(root: Path, service: CorpusService) -> None:
    """A store made before US-8.2: its rows keep NULL, and the summary counts them unclassified."""
    store = service.user_store("default", create=True)
    store.create_case("old")
    directory = store.directory
    service.close()
    with sqlite3.connect(directory / DATABASE) as db:
        db.execute("DROP TABLE outcomes")
        db.execute(
            "CREATE TABLE outcomes (case_id TEXT PRIMARY KEY REFERENCES cases(case_id), "
            "outcome TEXT NOT NULL CHECK (outcome IN ('overturned', 'upheld', 'written_off')), "
            "recorded_at TEXT NOT NULL) STRICT"
        )
        db.execute("INSERT INTO outcomes VALUES ('old', 'upheld', ?)", (IN_WEEK.isoformat(),))
    share(root, "default")
    before = summarize(root)
    assert before.totals.upheld == 1, "an unmigrated table is read without features"
    assert before.by_category == [
        CategoryRow(payer=None, denial_reason=None, upheld=1),
    ]

    reopened = service.user_store("default")  # the worker opens it again: migrated once
    with sqlite3.connect(directory / DATABASE) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(outcomes)")]
        assert columns == ["case_id", "outcome", "recorded_at", "features"]
        assert reopened.outcome("old") is not None


# --- The summary ---------------------------------------------------------------------------------


def test_us_8_2_counts_and_overturn_rate(root: Path, service: CorpusService) -> None:
    share(root, "default")
    share(root, "b")
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    record(service, "default", "a2", CaseOutcome.OVERTURNED)
    record(service, "b", "b1", CaseOutcome.UPHELD)
    record(service, "b", "b2", CaseOutcome.WRITTEN_OFF, OTHER)
    record(service, "b", "b3", CaseOutcome.UPHELD, None)
    record(service, "b", "late", CaseOutcome.UPHELD, at=IN_WEEK + timedelta(days=7))

    summary = summarize(root)

    assert summary.profiles == ["default", "b"]
    assert summary.totals == OutcomeCounts(overturned=2, upheld=2, written_off=1)
    assert summary.totals.overturn_rate == 0.4
    assert [
        (row.payer, row.denial_reason, row.total, row.overturn_rate) for row in summary.by_category
    ] == [
        ("ACME Health", DenialReason.PRIOR_AUTHORIZATION, 3, 0.6667),
        ("Other Payer", DenialReason.TIMELY_FILING, 1, 0.0),
        (None, None, 1, 0.0),
    ]
    assert [(row.payer, row.code, row.total) for row in summary.by_code] == [
        ("ACME Health", "CO-197", 3),
        ("ACME Health", "N286", 3),
        ("Other Payer", "CO-29", 1),
    ]
    assert OutcomeCounts().overturn_rate is None
    assert OutcomeCounts.model_validate(dumped_counts := {"overturned": 1, "upheld": 1}).total == 2
    assert dumped_counts == {"overturned": 1, "upheld": 1}, "the input is not changed"
    for inconsistent in ({"upheld": 1, "total": 3}, {"overturned": 1, "overturn_rate": 0.5}):
        with pytest.raises(ValidationError):
            OutcomeCounts.model_validate(inconsistent)
    for malformed in ({"upheld": "many"}, [1, 2, 3]):
        with pytest.raises(ValidationError):
            OutcomeCounts.model_validate(malformed)
    assert OutcomeCounts.model_validate(summary.totals) == summary.totals
    dumped = summary.model_dump(mode="json")
    assert dumped["totals"] == {
        "overturned": 2,
        "upheld": 2,
        "written_off": 1,
        "total": 5,
        "overturn_rate": 0.4,
    }


def test_us_8_2_a_case_counts_once_per_code(root: Path, service: CorpusService) -> None:
    share(root, "default")
    twice = OutcomeFeatures(payer=None, denial_reason=None, codes=["CO-197", "CO-197"])
    record(service, "default", "a1", CaseOutcome.UPHELD, twice)
    assert [(r.payer, r.code, r.total) for r in summarize(root).by_code] == [(None, "CO-197", 1)]


def test_us_8_2_invalid_stored_features_count_as_unclassified(
    root: Path, service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    share(root, "default")
    store = service.user_store("default", create=True)
    store.create_case("c1")
    store.record_outcome("c1", CaseOutcome.UPHELD, features='{"payer": 7}', at=IN_WEEK)
    with caplog.at_level(logging.WARNING):
        summary = summarize(root)
    assert summary.by_category == [CategoryRow(payer=None, denial_reason=None, upheld=1)]
    assert "features are invalid" in caplog.text


def test_us_8_2_summary_is_strict() -> None:
    with pytest.raises(ValidationError):
        WeeklySummary.model_validate(
            summarize_body() | {"extra": "Jane Doe"}  # unknown keys are refused
        )
    with pytest.raises(ValidationError):
        OutcomeFeatures.model_validate({"payer": "ACME Health", "note": "Jane Doe"})


def summarize_body() -> dict[str, Any]:
    return {
        "week": WEEK,
        "starts_at": IN_WEEK,
        "ends_at": IN_WEEK,
        "timezone": "UTC",
        "profiles": [],
        "not_shared": 0,
        "totals": {},
    }


# --- The week ------------------------------------------------------------------------------------


def test_us_8_2_week_bounds_in_the_local_zone() -> None:
    start, end = week_bounds("2026-W43", NEW_YORK)
    assert start == datetime(2026, 10, 19, tzinfo=NEW_YORK)
    assert end == datetime(2026, 10, 26, tzinfo=NEW_YORK)
    # The week daylight saving time ends in (Sunday 2026-11-01) is an hour longer.
    dst_start, dst_end = week_bounds("2026-W44", NEW_YORK)
    assert dst_end.astimezone(UTC) - dst_start.astimezone(UTC) == timedelta(days=7, hours=1)
    assert dst_start.utcoffset() == timedelta(hours=-4)
    assert dst_end.utcoffset() == timedelta(hours=-5)
    local_start, local_end = week_bounds("2026-W43")
    assert local_start.tzinfo is not None
    assert local_start.date().isoweekday() == 1
    elapsed = local_end.astimezone(UTC) - local_start.astimezone(UTC)
    assert timedelta(days=7, hours=-1) <= elapsed <= timedelta(days=7, hours=1)


def test_us_8_2_last_completed_week_is_judged_locally() -> None:
    sunday_night_in_new_york = datetime(2026, 11, 2, 3, tzinfo=UTC)
    assert last_completed_week(sunday_night_in_new_york, NEW_YORK) == "2026-W43"
    assert last_completed_week(sunday_night_in_new_york, UTC) == "2026-W44"
    assert last_completed_week(datetime(2027, 1, 4, 12, tzinfo=UTC), UTC) == "2026-W53"
    assert last_completed_week(datetime(2026, 11, 4, tzinfo=UTC)) in {"2026-W44", "2026-W45"}


def test_us_8_2_default_week_and_zone(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_module, "utc_now", lambda: datetime(2026, 10, 28, 12, tzinfo=UTC))
    summary = build_weekly_summary(root, tz=NEW_YORK)
    assert (summary.week, summary.timezone) == ("2026-W43", "America/New_York")
    assert (summary.profiles, summary.not_shared, summary.by_category) == ([], 0, [])
    assert build_weekly_summary(root, "2026-W43").timezone  # this Mac's zone, by name if known


def test_us_8_2_the_local_zone_is_named(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: the IANA name, not an abbreviation that names one side of a DST change."""
    zoneinfo = tmp_path / "var" / "db" / "timezone" / "zoneinfo" / "America"
    zoneinfo.mkdir(parents=True)
    (zoneinfo / "Chicago").write_bytes(b"")
    link = tmp_path / "localtime"
    link.symlink_to(zoneinfo / "Chicago")
    monkeypatch.setattr(summary_module, "LOCALTIME", link)
    assert build_weekly_summary(root, "2026-W44").timezone == "America/Chicago"
    monkeypatch.setattr(summary_module, "LOCALTIME", tmp_path / "missing")
    assert build_weekly_summary(root, "2026-W44").timezone == week_bounds("2026-W44")[0].tzname()


@pytest.mark.parametrize(
    "week",
    [
        *("2026-W54", "2026-W00", "2027-W53", "2026-43", "W43", ""),
        *("9999-W52", "0001-W01", "1969-W30", "\u0662\u0660\u0662\u0666-W43"),
    ],
)
def test_us_8_2_invalid_weeks(root: Path, week: str) -> None:
    with pytest.raises(ValidationError):
        build_weekly_summary(root, week)


def test_us_8_2_zone_name_without_tzname(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_module, "LOCALTIME", tmp_path / "missing")
    naive_zone = summary_module._zone_name(datetime(2026, 10, 19), None)
    assert naive_zone == "local"


# --- Routes --------------------------------------------------------------------------------------


@pytest.fixture
def worker(service: CorpusService) -> FastAPI:
    return create_app(TOKEN, corpus=service)


@pytest.fixture
async def desktop(
    worker: FastAPI, root: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over ``worker``."""
    monkeypatch.setenv("HERMES_HOME", str(root))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


async def test_us_8_2_summary_through_the_gateway(
    desktop: httpx.AsyncClient, root: Path, service: CorpusService
) -> None:
    share(root, "default")
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    response = await desktop.get(f"{PREFIX}/outcomes/summary", params={"week": WEEK})
    assert response.status_code == 200, response.text
    summary = WeeklySummary.model_validate_json(response.content)
    assert (summary.week, summary.totals.overturned) == (WEEK, 1)
    assert summary.by_category[0].payer == "ACME Health"
    latest = await desktop.get(f"{PREFIX}/outcomes/summary")
    assert latest.status_code == 200, latest.text


@pytest.mark.parametrize(
    "week",
    [
        "2027-W53",
        "26-W1",
        "2026-W43;drop",
        "x",
        "9999-W52",
        "0001-W01",
        "\u0662\u0660\u0662\u0666-W43",
    ],
)
async def test_us_8_2_bad_weeks_through_the_gateway(desktop: httpx.AsyncClient, week: str) -> None:
    response = await desktop.get(f"{PREFIX}/outcomes/summary", params={"week": week})
    assert_envelope(response, 422, "invalid_request")


# --- Review: one oversized or foreign row never fails the summary --------------------------------


async def test_us_8_2_a_huge_claim_keeps_a_summary_snapshot(service: CorpusService) -> None:
    """A claim of hundreds of lines is stored without its claim facts, under the read limit."""
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    read = {"status": "extracted"}
    line = {
        "procedure_code": read | {"value": "99213"},
        "service_date": read | {"value": "2026-09-01"},
        "billed_amount": read | {"value": "250.00"},
        "paid_amount": read | {"value": "0.00"},
        "adjustments": [
            {
                "group_code": read | {"value": "CO"},
                "carc": read | {"value": "197"},
                "amount": read | {"value": "1.00"},
            }
        ]
        * 9,
    }
    extraction = CaseExtraction.model_validate(
        {
            "payer_name": read | {"value": "ACME HEALTH PLAN"},
            "claim_id": read | {"value": "CLAIM-77"},
            "billed_amount": read | {"value": "250.00"},
            "paid_amount": read | {"value": "0.00"},
            "lines": [line] * 400,
        }
    )
    cases.save_extraction("default", case_id, extraction)
    cases.save_diagnosis(
        "default",
        case_id,
        Diagnosis(
            denial_reason=DenialReason.PRIOR_AUTHORIZATION,
            appeal_likelihood=AppealLikelihood.HIGH,
            likelihood_reasons=["Missing authorization."],
            codes=["CO-197"],
            extraction_digest=extraction.digest(),
            diagnosed_at=datetime.now(UTC),
        ),
    )
    full = outcome_features(extraction, cases.diagnosis(service.user_store("default"), case_id))
    assert full is not None
    assert len(full.model_dump_json()) > MAX_FEATURES_CHARS, "the case is too large to export"

    cases.record_outcome("default", case_id, CaseOutcome.UPHELD)

    (row,) = read_outcomes(
        service.user_store("default").directory,
        datetime.now(UTC) - timedelta(hours=1),
        datetime.now(UTC) + timedelta(hours=1),
    )
    assert row.features is not None
    stored = OutcomeFeatures.model_validate_json(row.features)
    assert (stored.denial_reason, stored.codes, stored.facts) == (
        DenialReason.PRIOR_AUTHORIZATION,
        ["CO-197"],
        None,
    )


def test_us_8_2_an_oversized_stored_snapshot_is_unclassified(
    root: Path, service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    """Review: a row no current version wrote counts as unclassified; the summary still works."""
    share(root, "default")
    store = service.user_store("default", create=True)
    store.create_case("c1")
    huge = '{"payer": "' + "x" * MAX_FEATURES_CHARS + '"}'
    store.record_outcome("c1", CaseOutcome.UPHELD, features=huge, at=IN_WEEK)
    with caplog.at_level(logging.WARNING):
        summary = summarize(root)
    assert summary.by_category == [CategoryRow(payer=None, denial_reason=None, upheld=1)]
    assert "too long" in caplog.text


def test_us_8_2_a_foreign_row_fails_only_its_profile(root: Path, service: CorpusService) -> None:
    share(root, "default")
    share(root, "b")
    record(service, "default", "a1", CaseOutcome.OVERTURNED)
    store = service.user_store("b", create=True)
    store.create_case("b1")
    directory = store.directory
    service.close()
    with sqlite3.connect(directory / DATABASE) as db:
        db.execute(
            "INSERT INTO outcomes VALUES ('b1', 'upheld', ?, NULL)",
            (IN_WEEK.isoformat().replace("+00:00", "x"),),  # sorts in the week, not a date
        )
    summary = summarize(root)
    assert (summary.profiles, summary.unreadable, summary.totals.total) == (["default"], ["b"], 1)
