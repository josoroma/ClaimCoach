"""US-8.1 Record a Case Outcome (Python half).

Scenarios: outcome is recorded on the case; a later outcome corrects the first; an outcome while a
job runs; an invalid outcome. Also: the case shows its outcome, the store transaction, and the
gateway route. The pane scenarios run under ``node --test``
(``plugin/desktop/tests/case_outcome.test.mjs``).
Rules: ES-1, ES-4, ES-8, BR-2, BR-7, BR-14.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient, WorkerRejectedError
from claimcoach.cases.intake import UploadedFile
from claimcoach.cases.models import Case, OutcomeRequest, PastedText
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CaseClosedError
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseOutcome, PurgeRequest
from claimcoach.events import Report
from claimcoach.models.manager import ModelEndpoint
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.diagnose import Diagnoser
from claimcoach.pipeline.extract import Extractor
from claimcoach.pipeline.jobs import JobRegistry
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, add_case_document, make_service
from tests.fakes.eob import synthetic_eob_pdf
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope, new_case, open_case


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(service: CorpusService) -> FastAPI:
    """A worker without models: recording an outcome runs no model."""
    return create_app(TOKEN, corpus=service)


@pytest.fixture
async def desktop(
    worker: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over ``worker``."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


async def mark(desktop: httpx.AsyncClient, case_id: str, body: Any) -> httpx.Response:
    return await desktop.post(f"{PREFIX}/cases/{case_id}/outcome", json=body)


async def marked(desktop: httpx.AsyncClient, case_id: str, outcome: str) -> Case:
    response = await mark(desktop, case_id, {"outcome": outcome})
    assert response.status_code == 200, response.text
    return Case.model_validate_json(response.content)


# --- Scenario: Outcome is recorded on the case ---------------------------------------------------


@pytest.mark.parametrize("outcome", list(CaseOutcome))
async def test_us_8_1_outcome_recorded(
    desktop: httpx.AsyncClient, service: CorpusService, outcome: CaseOutcome
) -> None:
    case_id = await new_case(desktop)
    assert (await open_case(desktop, case_id)).closed_at is None

    case = await marked(desktop, case_id, outcome.value)

    assert case.outcome is not None
    assert (case.outcome.case_id, case.outcome.outcome) == (case_id, outcome)
    assert case.closed_at is not None, "recording the outcome closes the case"
    assert case.closed_at == case.outcome.recorded_at
    store = service.user_store("default")
    stored = store.outcome(case_id)
    assert stored is not None
    assert stored.outcome is outcome
    assert store.case_record(case_id).closed_at == case.closed_at
    actions = [entry.action for entry in store.audit_log(case_id)]
    assert actions[-2:] == [AuditAction.OUTCOME_RECORDED, AuditAction.CASE_CLOSED]
    pasted = await desktop.post(f"{PREFIX}/cases/{case_id}/paste", json={"text": "More text."})
    assert_envelope(pasted, 409, "case_closed")


async def test_us_8_1_case_shows_its_outcome(desktop: httpx.AsyncClient) -> None:
    case_id = await new_case(desktop)
    assert (await open_case(desktop, case_id)).outcome is None
    await marked(desktop, case_id, "upheld")
    opened = await open_case(desktop, case_id)
    assert opened.outcome is not None
    assert opened.outcome.outcome is CaseOutcome.UPHELD


def test_us_8_1_outcome_and_close_are_one_transaction(service: CorpusService) -> None:
    """The store writes both, with the outcome's date as the close date."""
    store = service.user_store("default", create=True)
    store.create_case("c1")
    at = datetime(2026, 10, 20, 9, tzinfo=UTC)
    record = store.record_outcome("c1", CaseOutcome.WRITTEN_OFF, at=at)
    assert record.recorded_at == at
    assert store.case_record("c1").closed_at == at
    assert store.expired_cases(at + timedelta(days=1)) == []  # no content: nothing to purge


# --- Scenario: A later outcome corrects the first ------------------------------------------------


async def test_us_8_1_a_later_outcome_corrects_the_first(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await new_case(desktop)
    first = await marked(desktop, case_id, "overturned")
    second = await marked(desktop, case_id, "upheld")

    assert second.outcome is not None
    assert first.outcome is not None
    assert second.outcome.outcome is CaseOutcome.UPHELD
    assert second.outcome.recorded_at >= first.outcome.recorded_at
    assert second.closed_at == first.closed_at, "a correction never restarts the retention clock"
    actions = [entry.action for entry in service.user_store("default").audit_log(case_id)]
    assert actions.count(AuditAction.OUTCOME_RECORDED) == 2
    assert actions.count(AuditAction.CASE_CLOSED) == 1, "only the first outcome closed it"


async def test_us_8_1_a_purged_case_takes_a_correction(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    """The outcome is de-identified, so it outlives the purge and can still be corrected."""
    store = service.user_store("default", create=True)
    add_case_document(store, "c_old", "Denied CO-18.", closed_days_ago=200)
    service.purge(PurgeRequest(profile="default", case_id="c_old", confirm=True))
    case = await marked(desktop, "c_old", "written_off")
    assert case.outcome is not None
    assert case.outcome.outcome is CaseOutcome.WRITTEN_OFF
    assert case.documents == []
    assert case.closed_at == store.case_record("c_old").closed_at


# --- Scenario: An outcome while a job runs --------------------------------------------------------


async def test_us_8_1_outcome_refused_while_a_job_runs(
    desktop: httpx.AsyncClient, worker: FastAPI, service: CorpusService
) -> None:
    case_id = await new_case(desktop)
    running = {("default", case_id)}
    worker.state.jobs = SimpleNamespace(
        running=lambda profile, case: object() if (profile, case) in running else None
    )

    assert_envelope(await mark(desktop, case_id, {"outcome": "overturned"}), 409, "model_busy")
    assert service.user_store("default").outcome(case_id) is None
    assert (await open_case(desktop, case_id)).closed_at is None, "nothing is stored"

    running.clear()  # the job ended
    assert (await marked(desktop, case_id, "overturned")).closed_at is not None


class Blocked:
    """A job runner that runs until ``release`` is set."""

    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def run(self, _profile: str, _case_id: str, _report: Report) -> object:
        await self.release.wait()
        return None


async def test_us_8_1_outcome_waits_for_a_real_job(worker: FastAPI, service: CorpusService) -> None:
    """With the worker's own ``JobRegistry``: refused while the job runs, recorded once it ends."""
    runner = Blocked()
    registry = JobRegistry(runner)
    worker.state.jobs = registry
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    case_id = (await client.create_case("default")).case_id
    await client.paste_text("default", case_id, PastedText(text="Denied CO-197."))
    started = await client.start_extraction("default", case_id)
    assert registry.running("default", case_id) == started

    with pytest.raises(WorkerRejectedError) as refused:
        await client.record_outcome("default", case_id, OutcomeRequest(outcome=CaseOutcome.UPHELD))
    assert refused.value.code == "model_busy"
    assert service.user_store("default").outcome(case_id) is None

    runner.release.set()
    while registry.running("default", case_id) is not None:
        await asyncio.sleep(0.01)
    case = await client.record_outcome(
        "default", case_id, OutcomeRequest(outcome=CaseOutcome.UPHELD)
    )
    assert case.closed_at is not None


@pytest.mark.parametrize("runner", [Extractor, Diagnoser])
async def test_us_8_1_a_job_on_a_case_closed_meanwhile_holds_no_model(
    service: CorpusService, runner: type[Extractor] | type[Diagnoser]
) -> None:
    """Review: an outcome recorded between the busy check and the job's start stops the job."""
    cases = CaseService(service)
    case_id = cases.create("default").case_id
    cases.add_text("default", case_id, ERA_835)
    cases.add_file(
        "default",
        case_id,
        UploadedFile(filename="eob.pdf", content_type="application/pdf", data=synthetic_eob_pdf()),
    )
    cases.record_outcome("default", case_id, CaseOutcome.UPHELD)
    asked: list[ModelRole] = []

    @asynccontextmanager
    async def models(role: ModelRole) -> AsyncIterator[ModelEndpoint]:
        asked.append(role)
        yield ModelEndpoint(role=role, base_url="http://127.0.0.1:9/v1")

    with pytest.raises(CaseClosedError):
        await runner(cases, models).run("default", case_id, lambda _s, _p: None)
    assert asked == []


# --- Scenario: An invalid outcome ----------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"outcome": "won"},
        {"outcome": "Overturned"},
        {"outcome": "upheld", "note": "Called Jane Doe at the payer"},
        {},
        [],
        "upheld",
    ],
)
async def test_us_8_1_invalid_outcomes(
    desktop: httpx.AsyncClient, service: CorpusService, body: Any
) -> None:
    case_id = await new_case(desktop)
    response = await mark(desktop, case_id, body)
    assert_envelope(response, 422, "invalid_request")
    assert "Jane" not in response.text
    assert service.user_store("default").outcome(case_id) is None


async def test_us_8_1_outcome_refusals(desktop: httpx.AsyncClient) -> None:
    await new_case(desktop)  # the profile's store exists
    assert_envelope(await mark(desktop, "c_unknown", {"outcome": "upheld"}), 404, "case_not_found")
    assert_envelope(await mark(desktop, "bad id!", {"outcome": "upheld"}), 422, "invalid_request")
    as_text = await desktop.post(
        f"{PREFIX}/cases/c_unknown/outcome",
        content=b'{"outcome": "upheld"}',
        headers={"Content-Type": "text/plain"},
    )
    assert_envelope(as_text, 422, "invalid_request")


async def test_us_8_1_outcome_through_the_worker(worker: FastAPI, service: CorpusService) -> None:
    """The client posts the typed body to the worker with the profile."""
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    created = await client.create_case("biller-b")
    case = await client.record_outcome(
        "biller-b", created.case_id, OutcomeRequest(outcome=CaseOutcome.OVERTURNED)
    )
    assert case.outcome is not None
    assert case.outcome.outcome is CaseOutcome.OVERTURNED
    assert service.user_store("biller-b").outcome(created.case_id) is not None
