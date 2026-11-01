"""US-8.3 Manager-Approved Fine-Tune Export (Python half).

Scenarios: export requires manager approval; exported pairs contain no PHI. Also: what a record
holds, which outcomes become records, the opt-in, the owner-only files and the approval log, a
failed write, and the routes.
Rules: ES-1, ES-4, ES-8, BR-7, BR-13, BR-14, PRD §9.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.diagnosis import AppealLikelihood, DenialReason
from claimcoach.cases.extraction import FieldConfirmation
from claimcoach.cases.service import CaseService
from claimcoach.corpus.paths import FINE_TUNE_DIR, fine_tune_dir, profile_home
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import CaseOutcome, OutcomeRow
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.outcomes import export as export_module
from claimcoach.outcomes.export import APPROVALS_FILE, export_fine_tune, fine_tune_record
from claimcoach.outcomes.features import ClaimFacts, OutcomeFeatures, payment
from claimcoach.outcomes.types import (
    ExportApproval,
    ExportNotApprovedError,
    FineTuneExport,
    FineTuneExportRequest,
    FineTuneRecord,
)
from claimcoach.pipeline.diagnose import Diagnoser
from claimcoach.pipeline.extract import Extractor
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import (
    CODE_BUNDLE,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
)
from tests.fakes.eob import eob_reply
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings, seeded_strings
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope

APPROVED = FineTuneExportRequest(approval=ExportApproval(manager="Dana Manager", approved=True))
NOW = datetime(2026, 10, 31, 18, tzinfo=UTC)
FACTS = ClaimFacts.model_validate(
    {
        "payment": "none",
        "lines": [
            {
                "procedure_code": "99213",
                "payment": "none",
                "adjustments": [{"group_code": "CO", "carc": "197"}],
                "remark_codes": ["N286"],
            }
        ],
    }
)
LABELED = OutcomeFeatures(
    payer="ACME Health",
    denial_reason=DenialReason.PRIOR_AUTHORIZATION,
    codes=["CO-197", "N286"],
    appeal_likelihood=AppealLikelihood.HIGH,
    facts=FACTS,
)


@pytest.fixture(scope="module")
def role_servers() -> Iterator[dict[ModelRole, FakeModelServer]]:
    """Fake Qwen3-VL-8B, Qwen3-8B, and Qwen3-14B, each answering its own role's prompt."""
    replies = {
        ModelRole.EXTRACTION: eob_reply(),
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
    home = profile_home(profile, root)
    home.mkdir(parents=True, exist_ok=True)
    config = {"plugins": {"entries": {"claimcoach": {"settings": {"share_outcome_stats": value}}}}}
    (home / "config.yaml").write_text(yaml.safe_dump(config))


def record(
    service: CorpusService,
    profile: str,
    case_id: str,
    outcome: CaseOutcome,
    features: OutcomeFeatures | None = LABELED,
) -> None:
    store = service.user_store(profile, create=True)
    store.create_case(case_id, at=NOW - timedelta(days=30))
    snapshot = None if features is None else features.model_dump_json()
    store.record_outcome(case_id, outcome, features=snapshot, at=NOW - timedelta(days=1))


def lines_of(exported: FineTuneExport) -> list[dict[str, Any]]:
    text = Path(exported.path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


async def diagnosed_case(
    service: CorpusService, models: Any, phi: str, confirm: dict[str, str] | None = None
) -> tuple[CaseService, str]:
    """A case of the synthetic 835 plus a document seeded with PHI, extracted and diagnosed."""
    await service.import_bundle(CODE_BUNDLE)
    await service.import_bundle(RULE_BUNDLE)
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    cases.add_text("default", case_id, phi)
    await Extractor(cases, models).run("default", case_id, lambda _s, _p: None)
    for path, value in (confirm or {}).items():
        cases.confirm_field("default", case_id, FieldConfirmation(path=path, value=value))
    await Diagnoser(cases, models).run("default", case_id, lambda _s, _p: None)
    return cases, case_id


# --- Scenario: Export requires manager approval --------------------------------------------------


@pytest.mark.parametrize(
    "request_body",
    [
        FineTuneExportRequest(),
        FineTuneExportRequest(approval=ExportApproval(manager="Dana Manager", approved=False)),
    ],
)
def test_us_8_3_export_requires_approval(
    root: Path,
    service: CorpusService,
    request_body: FineTuneExportRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)

    def no_read(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("an unapproved export read the outcomes")

    monkeypatch.setattr(export_module, "shared_outcomes", no_read)
    with pytest.raises(ExportNotApprovedError) as refused:
        export_fine_tune(root, request_body, now=NOW)
    assert (refused.value.code, refused.value.status_code) == ("export_not_approved", 403)
    assert not (root / "plugin-data" / "claimcoach" / FINE_TUNE_DIR).exists(), "no export file"


@pytest.mark.parametrize(
    "approval",
    [
        {"manager": "Dana Manager", "approved": "yes"},
        {"manager": "Dana Manager", "approved": 1},
        {"manager": "", "approved": True},
        {"manager": "   ", "approved": True},
        {"manager": "Dana\nManager", "approved": True},
        {"manager": "Dana\u2028Manager", "approved": True},
        {"manager": "Dana\u2029Manager", "approved": True},
        {"manager": "Dana\x85Manager", "approved": True},
        {"manager": "x" * 81, "approved": True},
        {"approved": True},
        {"manager": "Dana Manager", "approved": True, "scope": "all"},
    ],
)
def test_us_8_3_approval_is_strict(approval: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FineTuneExportRequest.model_validate({"approval": approval})


# --- Scenario: Exported pairs contain no PHI -----------------------------------------------------


async def test_us_8_3_exported_pairs_contain_no_phi(
    root: Path, service: CorpusService, models: Any
) -> None:
    document = PHI_DOCUMENTS[0]
    name = document["phi"]["name"][0]
    member_id = document["phi"]["member_id"][0]
    cases, case_id = await diagnosed_case(
        service, models, document["text"], confirm={"claim_id": member_id}
    )
    # Fields mis-read as a person's name or member ID stay out of the export too.
    mislabeled, other = await diagnosed_case(
        service, models, document["text"], confirm={"payer_name": name, "claim_id": member_id}
    )
    cases.record_outcome("default", case_id, CaseOutcome.OVERTURNED)
    mislabeled.record_outcome("default", other, CaseOutcome.UPHELD)
    share(root, "default")

    exported = export_fine_tune(root, APPROVED)

    text = Path(exported.path).read_text(encoding="utf-8")
    assert exported.records == 2
    assert list(seeded_strings(document)), "the fixture seeds PHI"
    assert leaked_strings(text, document) == []
    for case_text in (
        "CLAIM-77",
        "PCN-0001",
        "SYNTHETIC",
        "2026-09-01",
        "2026-10-15",
        "250",
        case_id,
    ):
        assert case_text not in text, case_text
    assert leaked_strings(exported.model_dump_json(), document) == []


async def test_us_8_3_a_record_is_what_the_classifier_read(
    root: Path, service: CorpusService, models: Any
) -> None:
    cases, case_id = await diagnosed_case(service, models, "Denial notice: see the remittance.")
    cases.record_outcome("default", case_id, CaseOutcome.OVERTURNED)
    share(root, "default")

    exported = export_fine_tune(root, APPROVED, now=datetime.now(UTC) + timedelta(seconds=1))

    (line,) = lines_of(exported)
    assert FineTuneRecord.model_validate(line) == FineTuneRecord(
        format="claimcoach-fine-tune-1",
        payer="ACME Health",
        facts=FACTS,
        codes=["CO-197", "N286"],
        denial_reason=DenialReason.PRIOR_AUTHORIZATION,
        appeal_likelihood=AppealLikelihood.HIGH,
        outcome=CaseOutcome.OVERTURNED,
    )
    assert set(line) == {
        "format",
        "payer",
        "facts",
        "codes",
        "denial_reason",
        "appeal_likelihood",
        "outcome",
    }


# --- Which outcomes become records ---------------------------------------------------------------


def test_us_8_3_only_labeled_outcomes_of_sharing_profiles(
    root: Path, service: CorpusService
) -> None:
    share(root, "default")
    record(service, "default", "labeled", CaseOutcome.OVERTURNED)
    record(service, "default", "summary_only", CaseOutcome.UPHELD, OutcomeFeatures(payer="X"))
    no_facts = LABELED.model_copy(update={"facts": None})
    record(service, "default", "before_us_8_3", CaseOutcome.UPHELD, no_facts)
    record(service, "default", "before_us_8_2", CaseOutcome.UPHELD, None)
    record(service, "b", "not_shared", CaseOutcome.WRITTEN_OFF)

    exported = export_fine_tune(root, APPROVED, now=NOW)

    assert (exported.records, exported.unlabeled, exported.withheld) == (1, 3, 0)
    assert (exported.profiles, exported.unreadable) == (["default"], [])
    assert [line["outcome"] for line in lines_of(exported)] == ["overturned"]


def test_us_8_3_records_of_invalid_snapshots_are_left_out() -> None:
    row = OutcomeRow(outcome=CaseOutcome.UPHELD, recorded_at=NOW, features='{"payer": 7}')
    assert fine_tune_record(row) is None


def test_us_8_3_a_record_a_validator_matches_is_withheld(
    root: Path, service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    """The last guard: a record the US-3.1 regex validators match is never written."""
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    record(
        service,
        "default",
        "c2",
        CaseOutcome.UPHELD,
        LABELED.model_copy(update={"payer": "SSN 123-45-6789"}),
    )
    with caplog.at_level(logging.INFO):
        exported = export_fine_tune(root, APPROVED, now=NOW)
    assert (exported.records, exported.withheld) == (1, 1)
    assert "123-45-6789" not in Path(exported.path).read_text()
    assert "123-45-6789" not in caplog.text
    assert "1 records (0 unlabeled, 1 withheld)" in caplog.text


def test_us_8_3_an_export_with_nothing_shared_is_empty(root: Path) -> None:
    exported = export_fine_tune(root, APPROVED, now=NOW)
    assert (exported.records, exported.profiles) == (0, [])
    assert Path(exported.path).read_bytes() == b""


# --- Files ---------------------------------------------------------------------------------------


def test_us_8_3_files_are_owner_only_and_approvals_logged(
    root: Path, service: CorpusService
) -> None:
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    first = export_fine_tune(root, APPROVED, now=NOW)
    second = export_fine_tune(
        root,
        FineTuneExportRequest(approval=ExportApproval(manager=" Lee Manager ", approved=True)),
        now=NOW,
    )

    folder = fine_tune_dir(root)
    assert folder == root / "plugin-data" / "claimcoach" / "fine-tune"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert first.path != second.path, "an export never replaces another"
    assert first.filename.startswith("fine-tune-20261031T180000Z-")
    for path in (Path(first.path), Path(second.path), folder / APPROVALS_FILE):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    log = [json.loads(line) for line in (folder / APPROVALS_FILE).read_text().splitlines()]
    assert log == [
        {
            "filename": first.filename,
            "records": 1,
            "profiles": ["default"],
            "approved_by": "Dana Manager",
            "approved_at": "2026-10-31T18:00:00Z",
        },
        {
            "filename": second.filename,
            "records": 1,
            "profiles": ["default"],
            "approved_by": "Lee Manager",
            "approved_at": "2026-10-31T18:00:00Z",
        },
    ]
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [first.filename, second.filename, APPROVALS_FILE]
    )


def exports_in(root: Path) -> list[str]:
    return sorted(p.name for p in fine_tune_dir(root).glob("fine-tune-*.jsonl"))


def failing_fdopen(monkeypatch: pytest.MonkeyPatch, failing_mode: str) -> None:
    """Make writes through ``os.fdopen`` in ``failing_mode`` fail as a full disk would."""
    real_fdopen = os.fdopen

    class Full:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> Full:
            return self

        def __exit__(self, *_exc: object) -> None:
            self.handle.close()

        def write(self, _data: object) -> int:
            raise OSError("disk full")

    def fdopen(fd: int, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        handle = real_fdopen(fd, mode, *args, **kwargs)
        return Full(handle) if mode == failing_mode else handle

    monkeypatch.setattr(os, "fdopen", fdopen)  # the export module's os is this one


def test_us_8_3_a_failed_write_leaves_nothing(
    root: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    failing_fdopen(monkeypatch, "wb")
    with pytest.raises(OSError, match="disk full"):
        export_fine_tune(root, APPROVED, now=NOW)
    assert sorted(p.name for p in fine_tune_dir(root).iterdir()) == [APPROVALS_FILE]
    assert (fine_tune_dir(root) / APPROVALS_FILE).read_text() == "", "no approval logged"


def test_us_8_3_an_export_is_never_left_unlogged(
    root: Path, service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: the approval log failing after the export was written removes the export."""
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    failing_fdopen(monkeypatch, "a")
    with pytest.raises(OSError, match="disk full"):
        export_fine_tune(root, APPROVED, now=NOW)
    assert exports_in(root) == []


def test_us_8_3_the_approval_log_is_never_followed_through_a_link(
    root: Path, service: CorpusService, tmp_path: Path
) -> None:
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    folder = fine_tune_dir(root)
    elsewhere = tmp_path / "elsewhere.jsonl"
    elsewhere.write_text("")
    (folder / APPROVALS_FILE).symlink_to(elsewhere)
    with pytest.raises(OSError, match="Too many levels of symbolic links"):
        export_fine_tune(root, APPROVED, now=NOW)
    assert elsewhere.read_text() == ""
    assert exports_in(root) == [], "review: no export without its log line"


def test_us_8_3_the_approval_log_must_be_a_regular_file(root: Path) -> None:
    """Review: a FIFO or a folder at the log's path stops the export before any file is written."""
    folder = fine_tune_dir(root)
    fifo = folder / APPROVALS_FILE
    os.mkfifo(fifo, 0o600)
    with pytest.raises(OSError, match="Device not configured"):
        export_fine_tune(root, APPROVED, now=NOW)  # no reader: O_NONBLOCK refuses, never hangs
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        with pytest.raises(OSError, match="not this user's regular file"):
            export_fine_tune(root, APPROVED, now=NOW)  # a reader waits: still not a log
    finally:
        os.close(reader)
    assert exports_in(root) == []


def test_us_8_3_an_existing_log_is_made_owner_only(root: Path) -> None:
    log = fine_tune_dir(root) / APPROVALS_FILE
    log.write_text("")
    log.chmod(0o644)  # a copy restored with another mode
    export_fine_tune(root, APPROVED, now=NOW)
    assert stat.S_IMODE(log.stat().st_mode) == 0o600


def test_us_8_3_the_fine_tune_folder_is_never_a_link(root: Path, tmp_path: Path) -> None:
    """Review: a link in the folder's place would send exports wherever it points."""
    synced = tmp_path / "synced"
    synced.mkdir()
    data = root / "plugin-data" / "claimcoach"
    data.mkdir(parents=True)
    (data / FINE_TUNE_DIR).symlink_to(synced)
    with pytest.raises(OSError, match="must not be a symbolic link"):
        export_fine_tune(root, APPROVED, now=NOW)
    assert list(synced.iterdir()) == []


def test_us_8_3_outcomes_recorded_after_a_clock_change_are_exported(
    root: Path, service: CorpusService
) -> None:
    """Review: an outcome stamped after "now" (the clock was set back since) is still exported."""
    share(root, "default")
    store = service.user_store("default", create=True)
    store.create_case("c1")
    store.record_outcome(
        "c1", CaseOutcome.UPHELD, features=LABELED.model_dump_json(), at=NOW + timedelta(days=3)
    )
    assert export_fine_tune(root, APPROVED, now=NOW).records == 1


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


async def test_us_8_3_export_through_the_gateway(
    desktop: httpx.AsyncClient, root: Path, service: CorpusService
) -> None:
    share(root, "default")
    record(service, "default", "c1", CaseOutcome.OVERTURNED)
    response = await desktop.post(
        f"{PREFIX}/outcomes/export",
        json={"approval": {"manager": "Dana Manager", "approved": True}},
    )
    assert response.status_code == 200, response.text
    exported = FineTuneExport.model_validate_json(response.content)
    assert (exported.records, exported.approved_by) == (1, "Dana Manager")
    assert Path(exported.path).is_file()


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({}, 403, "export_not_approved"),
        ({"approval": None}, 403, "export_not_approved"),
        ({"approval": {"manager": "Dana Manager", "approved": False}}, 403, "export_not_approved"),
        ({"approval": {"manager": "Dana Manager", "approved": "true"}}, 422, "invalid_request"),
        (
            {"approval": {"manager": "Dana Manager", "approved": True}, "all": 1},
            422,
            "invalid_request",
        ),
        ([], 422, "invalid_request"),
    ],
)
async def test_us_8_3_refusals_through_the_gateway(
    desktop: httpx.AsyncClient, root: Path, body: Any, status: int, code: str
) -> None:
    response = await desktop.post(f"{PREFIX}/outcomes/export", json=body)
    assert_envelope(response, status, code)
    assert not (root / "plugin-data" / "claimcoach" / FINE_TUNE_DIR).exists()
    as_text = await desktop.post(
        f"{PREFIX}/outcomes/export",
        content=json.dumps(body).encode(),
        headers={"Content-Type": "text/plain"},
    )
    assert_envelope(as_text, 422, "invalid_request")


@pytest.mark.parametrize(
    ("billed", "paid", "status"),
    [
        ("250.00", "0.00", "none"),
        ("250.00", "-5.00", "none"),
        ("250.00", "100.00", "partial"),
        ("250.00", "250.00", "full"),
        ("250.00", "300.00", "full"),
        (None, "0.00", None),
        ("250.00", None, None),
    ],
)
def test_us_8_3_amounts_are_reduced_to_a_payment_status(
    billed: str | None, paid: str | None, status: str | None
) -> None:
    """Review: no dollar amount is kept, only whether the charge was paid."""

    def as_decimal(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    assert payment(as_decimal(billed), as_decimal(paid)) == status
    schema = ClaimFacts.model_json_schema()
    fields = {name for model in schema["$defs"].values() for name in model["properties"]}
    fields |= set(schema["properties"])
    assert not [name for name in fields if "amount" in name], fields
