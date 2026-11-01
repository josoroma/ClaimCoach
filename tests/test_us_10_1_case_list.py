"""US-10.1 Case Pane and Manager Dashboard Route (Python half).

Scenarios: the case pane is registered with its case list and case detail views; the dashboard
route is registered; backend errors render as an error state. The registrations and the error
state run under ``node --test`` (``plugin/desktop/tests/desktop_ui.test.mjs``); this module covers
the case list the pane reads: ``GET /cases`` through the gateway and the worker, without case
content and without an audit entry.
Rules: ES-1, ES-4, ES-8, BR-2, BR-14.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.models import MAX_LISTED_CASES, CaseList
from claimcoach.cases.service import CaseService
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, CaseOutcome, utc_now
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope

PAYER = "ACME HEALTH PLAN"
LETTER = f"{PAYER} denied claim CLAIM-77 for Jane Doe."


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
async def desktop(
    service: CorpusService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over a worker without models."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    worker = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


async def listed(desktop: httpx.AsyncClient) -> CaseList:
    response = await desktop.get(f"{PREFIX}/cases")
    assert response.status_code == 200, response.text
    return CaseList.model_validate_json(response.content)


def mark_item(service: CorpusService, case_id: str, kind: str) -> None:
    item = CaseItem.model_validate(
        {
            "case_id": case_id,
            "item_id": kind,
            "kind": kind,
            "created_at": utc_now(),
            "payload": b"{}",
        }
    )
    service.user_store("default").put_case_item(item, audit=AuditAction.CASE_EXTRACTED)


# --- Scenario: The case pane is registered (its case list) ---------------------------------------


async def test_us_10_1_case_list_holds_no_content(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    first = (await desktop.post(f"{PREFIX}/cases", json={})).json()["case_id"]
    pasted = await desktop.post(f"{PREFIX}/cases/{first}/paste", json={"text": LETTER})
    assert pasted.status_code == 200, pasted.text
    second = (await desktop.post(f"{PREFIX}/cases", json={})).json()["case_id"]
    outcome = await desktop.post(f"{PREFIX}/cases/{second}/outcome", json={"outcome": "upheld"})
    assert outcome.status_code == 200, outcome.text
    store = service.user_store("default")
    before = len(store.audit_log())

    response = await desktop.get(f"{PREFIX}/cases")

    assert response.status_code == 200, response.text
    for secret in (PAYER, "CLAIM-77", "Jane"):
        assert secret not in response.text
    cases = CaseList.model_validate_json(response.content).cases
    assert {entry.case_id for entry in cases} == {first, second}
    by_id = {entry.case_id: entry for entry in cases}
    assert (by_id[first].documents, by_id[first].closed_at, by_id[first].outcome) == (1, None, None)
    assert by_id[second].outcome is CaseOutcome.UPHELD
    assert by_id[second].closed_at is not None
    assert len(store.audit_log()) == before, "listing is not a case access"


async def test_us_10_1_list_shows_steps_newest_first(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    store = service.user_store("default", create=True)
    start = datetime(2026, 10, 1, tzinfo=UTC)
    for day in range(3):
        store.create_case(f"case_{day:016x}", at=start + timedelta(days=day))
    mark_item(service, "case_0000000000000001", "extraction")
    mark_item(service, "case_0000000000000001", "diagnosis")
    mark_item(service, "case_0000000000000002", "draft")

    cases = (await listed(desktop)).cases

    assert [entry.case_id for entry in cases] == [
        "case_0000000000000002",
        "case_0000000000000001",
        "case_0000000000000000",
    ]
    steps = [(entry.extracted, entry.diagnosed, entry.drafted) for entry in cases]
    assert steps == [(False, False, True), (True, True, False), (False, False, False)]
    assert [entry.case_id for entry in store.case_index(1)] == ["case_0000000000000002"]


async def test_us_10_1_list_without_a_user_scope(desktop: httpx.AsyncClient) -> None:
    assert (await listed(desktop)).cases == [], "a new biller has no cases, not an error"


def test_us_10_1_list_is_bounded(service: CorpusService) -> None:
    cases = CaseService(service)
    store = service.user_store("default", create=True)
    for n in range(MAX_LISTED_CASES + 1):
        store.create_case(f"case_{n:016x}")
    assert len(cases.list_cases("default").cases) == MAX_LISTED_CASES


def test_us_10_1_global_scope_has_no_cases(service: CorpusService) -> None:
    with pytest.raises(CorpusError):
        service.global_store().case_index(10)


# --- Scenario: Backend errors render as an error state (the gateway's part) ----------------------


async def test_us_10_1_list_through_the_gateway_when_the_worker_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: None)
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        assert_envelope(await desktop.get(f"{PREFIX}/cases"), 503, "worker_unavailable")
