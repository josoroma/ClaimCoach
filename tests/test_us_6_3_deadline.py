"""US-6.3 Appeal Deadline (Python half).

Scenario: deadline is computed from the rule card. Also: the pure ``compute_deadline``, why an
unknown deadline is unknown (including an implausible date), the deadline computed whenever the
case is read (so a confirmed date or a re-imported card shows at once, and a failed model hides
nothing), the denial date read from the right 835 transaction and confirmable as ``YYYY-MM-DD``
only, older extractions without it, and the appeal limit on rule cards. The pane scenarios run under
``node --test`` (``plugin/desktop/tests/case_diagnosis.test.mjs``).
Rules: ES-1, ES-3, ES-4; PRD §9 (rule cards hold the appeal limits).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.diagnosis import AppealDeadline
from claimcoach.cases.extraction import CaseExtraction, FieldStatus, read_value
from claimcoach.cases.models import Case
from claimcoach.cases.service import EXTRACTION_ITEM, CaseService
from claimcoach.corpus.bundle import CorpusBundle, RuleCard
from claimcoach.corpus.lookup import rule_card_of
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import AuditAction, CaseItem, utc_now
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.pipeline import deadline as deadline_module
from claimcoach.pipeline.deadline import appeal_deadline, compute_deadline
from claimcoach.pipeline.edi835 import parse_835
from claimcoach.pipeline.extract import EXTRACTION_TEMPLATE
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.diagnosis import (
    ACME_DOCUMENTS,
    classification_reply,
    explanation_reply,
    role_models,
    rule_card,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import (
    PREFIX,
    Sent,
    assert_envelope,
    extracted_case,
    new_case,
    open_case,
    run_job,
)

DENIAL = date(2026, 10, 15)
"""The synthetic 835's BPR16 payment date (``ERA_835``)."""

ACME_RULES = CorpusBundle(
    items=[
        rule_card("ACME Health", "appeal_levels", appeal_limit_days=180),
        rule_card("ACME Health", "required_docs", required_documents=list(ACME_DOCUMENTS)),
    ]
)


@pytest.fixture(scope="module")
def classifier() -> Iterator[FakeModelServer]:
    with FakeModelServer() as server:
        yield server


@pytest.fixture(scope="module")
def explainer() -> Iterator[FakeModelServer]:
    with FakeModelServer() as server:
        yield server


@pytest.fixture(autouse=True)
def _reset_models(classifier: FakeModelServer, explainer: FakeModelServer) -> None:
    for server in (classifier, explainer):
        server.requests.clear()
    classifier.replies[DEFAULT_MODEL_ID] = classification_reply()
    explainer.replies[DEFAULT_MODEL_ID] = explanation_reply()


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
def worker(
    service: CorpusService, classifier: FakeModelServer, explainer: FakeModelServer
) -> FastAPI:
    models = role_models(
        {ModelRole.CLASSIFICATION: classifier.base_url, ModelRole.EXPLANATION: explainer.base_url}
    )
    return create_app(TOKEN, corpus=service, pipeline_models=models)


@pytest.fixture
def sent() -> Sent:
    return []


@pytest.fixture
async def desktop(
    worker: FastAPI, sent: Sent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    gateway.dependency_overrides[routes.get_event_sink] = lambda: (
        lambda plugin, event, payload: sent.append((plugin, event, payload))
    )
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


async def deadline_of(desktop: httpx.AsyncClient, case_id: str) -> AppealDeadline:
    deadline = (await open_case(desktop, case_id)).deadline
    assert deadline is not None
    return deadline


# --- Scenario: Deadline is computed from the rule card -------------------------------------------


async def test_us_6_3_deadline_from_rule_card(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    await service.import_bundle(ACME_RULES)
    case_id = await extracted_case(desktop)
    case = await open_case(desktop, case_id)
    assert case.extraction is not None
    assert case.extraction.denial_date.value == DENIAL, "the case has a denial date"

    await run_job(desktop, case_id, "diagnose")

    case = await open_case(desktop, case_id)
    assert case.diagnosis is not None, "diagnosis ran"
    deadline = await deadline_of(desktop, case_id)
    assert deadline == AppealDeadline(
        status="computed",
        due=DENIAL + timedelta(days=180),
        denial_date=DENIAL,
        limit_days=180,
        rule_card="ACME Health/appeal_levels",
    )
    assert deadline.due == date(2027, 4, 13)


# --- The pure computation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("denial", "limit", "due"),
    [
        (date(2026, 10, 15), 180, date(2027, 4, 13)),
        (date(2026, 10, 15), 1, date(2026, 10, 16)),
        (date(2027, 12, 31), 60, date(2028, 2, 29)),  # through a leap day
        (date(2026, 1, 31), 30, date(2026, 3, 2)),
    ],
)
def test_us_6_3_compute_deadline_is_pure(denial: date, limit: int, due: date) -> None:
    assert compute_deadline(denial, limit) == due
    assert compute_deadline(denial, limit) == due, "the same inputs give the same date"
    assert "US-6.3" in (compute_deadline.__doc__ or "")
    assert "US-6.3" in (deadline_module.__doc__ or "")


def test_us_6_3_compute_deadline_refuses_no_limit() -> None:
    with pytest.raises(ValueError, match="at least one day"):
        compute_deadline(DENIAL, 0)
    signature = inspect.signature(compute_deadline)
    assert [p.annotation for p in signature.parameters.values()] == ["date", "int"]
    assert signature.return_annotation == "date"


# --- Scenario: An unknown deadline says why -------------------------------------------------------


TODAY = date(2026, 10, 31)


def extraction_with(
    denial: str | None, *, payer: str | None = "ACME HEALTH PLAN", served: str = "2026-09-01"
) -> CaseExtraction:
    def field(value: str | None) -> dict[str, Any]:
        status = "unreadable" if value is None else "extracted"
        return {"value": value, "status": status}

    return CaseExtraction.model_validate(
        {
            "payer_name": field(payer),
            "claim_id": field("CLAIM-77"),
            "billed_amount": field("250.00"),
            "paid_amount": field("0.00"),
            "denial_date": field(denial),
            "lines": [
                {
                    "procedure_code": field("99213"),
                    "service_date": field(served),
                    "billed_amount": field("250.00"),
                    "paid_amount": field("0.00"),
                }
            ],
        }
    )


def test_us_6_3_unknown_deadline_says_why() -> None:
    dated, undated = extraction_with("2026-10-15"), extraction_with(None)
    levels = rule_card("ACME Health", "appeal_levels", appeal_limit_days=90)
    no_limit = rule_card("ACME Health", "appeal_levels")
    docs = rule_card("ACME Health", "required_docs", required_documents=["Form"])

    def status(extraction: CaseExtraction, cards: list[RuleCard]) -> str:
        return appeal_deadline(extraction, cards, TODAY).status

    no_payer = extraction_with("2026-10-15", payer=None)
    assert appeal_deadline(no_payer, [levels], TODAY) == AppealDeadline(
        status="no_payer", denial_date=DENIAL
    ), "the biller confirms the payer; no card can match an unread payer"
    assert appeal_deadline(dated, [], TODAY) == AppealDeadline(
        status="no_rule_card", denial_date=DENIAL
    )
    assert status(dated, [docs]) == "no_appeal_limit"
    assert status(dated, [no_limit, docs]) == "no_appeal_limit"
    assert status(undated, []) == "no_rule_card", "card problems come first"
    assert status(undated, [docs]) == "no_appeal_limit"
    assert appeal_deadline(undated, [levels], TODAY) == AppealDeadline(
        status="no_denial_date", limit_days=90, rule_card="ACME Health/appeal_levels"
    )
    computed = appeal_deadline(dated, [docs, levels], TODAY)
    assert (computed.status, computed.due) == ("computed", date(2027, 1, 13))


@pytest.mark.parametrize(
    ("denial", "served", "result"),
    [
        ("2026-11-01", "2026-09-01", "implausible_denial_date"),  # after today: a misread
        ("2027-10-15", "2026-09-01", "implausible_denial_date"),  # a year misread
        ("9999-12-31", "2026-09-01", "implausible_denial_date"),  # never reaches an overflow
        ("2026-08-31", "2026-09-01", "implausible_denial_date"),  # before the service
        ("2026-09-01", "2026-09-01", "computed"),  # denied the day of service
        ("2026-10-31", "2026-09-01", "computed"),  # denied today
    ],
)
def test_us_6_3_implausible_denial_date_is_not_used(denial: str, served: str, result: str) -> None:
    """US-6.3 review: a date the model misread never becomes a confident deadline."""
    levels = rule_card("ACME Health", "appeal_levels", appeal_limit_days=180)
    deadline = appeal_deadline(extraction_with(denial, served=served), [levels], TODAY)
    assert deadline.status == result
    if result != "computed":
        assert deadline.due is None
        assert deadline.denial_date == date.fromisoformat(denial)


def test_us_6_3_deadline_model_is_strict() -> None:
    with pytest.raises(ValidationError, match="only a computed deadline has a due date"):
        AppealDeadline(status="no_rule_card", due=DENIAL)
    with pytest.raises(ValidationError, match="only a computed deadline has a due date"):
        AppealDeadline(status="computed")
    with pytest.raises(ValidationError, match="names its date, limit, and card"):
        AppealDeadline(status="computed", due=DENIAL)
    with pytest.raises(ValidationError, match="its denial date plus its limit"):
        AppealDeadline(
            status="computed", due=DENIAL, denial_date=DENIAL, limit_days=1, rule_card="A/b"
        )
    with pytest.raises(ValidationError):
        AppealDeadline.model_validate({"status": "soon"})


async def test_us_6_3_no_rule_card(desktop: httpx.AsyncClient) -> None:
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    deadline = await deadline_of(desktop, case_id)
    assert (deadline.status, deadline.due, deadline.denial_date) == ("no_rule_card", None, DENIAL)


async def test_us_6_3_deadline_follows_the_case_without_a_model(
    desktop: httpx.AsyncClient, service: CorpusService, classifier: FakeModelServer
) -> None:
    """US-6.3 review: no model run hides or freezes the deadline."""
    case_id = await new_case(desktop)
    assert (await open_case(desktop, case_id)).deadline is None, "nothing before extraction"
    await run_job(desktop, case_id, "process")
    assert (await deadline_of(desktop, case_id)).status == "no_rule_card"

    # A card added after extraction shows at once, without diagnosing.
    await service.import_bundle(ACME_RULES)
    assert (await deadline_of(desktop, case_id)).due == date(2027, 4, 13)

    # The classification model fails: the deadline is still shown.
    classifier.replies[DEFAULT_MODEL_ID] = "not json"
    await run_job(desktop, case_id, "diagnose")
    case = await open_case(desktop, case_id)
    assert case.diagnosis is None
    assert case.deadline is not None
    assert case.deadline.status == "computed"

    # The payer cuts its limit: the re-imported card changes the deadline on the next read.
    await service.import_bundle(
        CorpusBundle(items=[rule_card("ACME Health", "appeal_levels", appeal_limit_days=90)])
    )
    assert (await deadline_of(desktop, case_id)).due == date(2027, 1, 13)


async def test_us_6_3_two_spellings_use_the_freshest_limit(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    """US-6.3 review: two appeal_levels cards of one payer never race; the newest is used."""
    today = date.today()
    await service.import_bundle(
        CorpusBundle(
            items=[
                rule_card(
                    "ACME Health",
                    "appeal_levels",
                    appeal_limit_days=180,
                    verified_on=today - timedelta(days=300),
                )
            ]
        )
    )
    await service.import_bundle(
        CorpusBundle(
            items=[
                rule_card(
                    "ACME HEALTH",
                    "appeal_levels",
                    appeal_limit_days=60,
                    verified_on=today - timedelta(days=2),
                )
            ]
        )
    )
    case_id = await extracted_case(desktop)
    deadline = await deadline_of(desktop, case_id)
    assert (deadline.limit_days, deadline.rule_card) == (60, "ACME HEALTH/appeal_levels")


async def test_us_6_3_unreadable_denial_date(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    await service.import_bundle(ACME_RULES)
    undated = ERA_835.replace("BPR*I*0*C*NON************20261015~", "BPR*I*0*C*NON~").replace(
        "*20261015*1200*1*X*", "**1200*1*X*"
    )
    case_id = await new_case(desktop, undated)
    await run_job(desktop, case_id, "process")
    case = await open_case(desktop, case_id)
    assert "denial_date" in case.needs_confirmation, "highlighted for the biller"

    await run_job(desktop, case_id, "diagnose")
    deadline = await deadline_of(desktop, case_id)
    assert (deadline.status, deadline.due, deadline.limit_days) == ("no_denial_date", None, 180)

    confirmed = await desktop.post(
        f"{PREFIX}/cases/{case_id}/fields", json={"path": "denial_date", "value": "2026-10-20"}
    )
    assert confirmed.status_code == 200, confirmed.text
    answer = Case.model_validate_json(confirmed.content)
    assert answer.deadline is not None
    assert (answer.deadline.status, answer.deadline.due) == ("computed", date(2027, 4, 18))
    assert (await deadline_of(desktop, case_id)).due == date(2027, 4, 18), "no re-diagnosis"


# --- Scenario: The 835 gives the denial date (case-extraction) -----------------------------------


def era(gs04: str = "20261015", bpr16: str = "20261015", dtm405: str | None = None) -> str:
    """The synthetic 835 with its GS04, BPR16, and an optional DTM*405 set."""
    text = ERA_835.replace("*20261015*1200*1*X*", f"*{gs04}*1200*1*X*").replace(
        "BPR*I*0*C*NON************20261015~", f"BPR*I*0*C*NON************{bpr16}~"
    )
    if dtm405 is not None:
        text = text.replace("TRN*1*12345*1512345678~", f"TRN*1*12345*1512345678~DTM*405*{dtm405}~")
    return text


def test_us_6_3_835_gives_the_denial_date() -> None:
    def denial(text: str) -> object:
        return parse_835(text)[0].denial_date

    assert denial(ERA_835) == "2026-10-15"
    assert denial(era(dtm405="20261012")) == "2026-10-12", "DTM*405 first"
    # US-6.3 review: without DTM*405 the production date is GS04, not the later BPR16 EFT date.
    assert denial(era(gs04="20261015", bpr16="20261019")) == "2026-10-15"
    assert denial(era(gs04="", bpr16="20261019")) == "2026-10-19", "BPR16 only without GS04"
    # A malformed or empty DTM*405 does not block the next source.
    assert denial(era(dtm405="20261340")) == "2026-10-15"
    assert denial(era(dtm405="")) == "2026-10-15"
    late = ERA_835.replace("SVC*HC:99213", "DTM*405*20261001~SVC*HC:99213")
    assert denial(late) == "2026-10-15", "a DTM*405 inside a claim is not the header's"
    assert denial(era(gs04="", bpr16="")) is None


def test_us_6_3_835_dates_come_from_the_first_claims_transaction() -> None:
    """US-6.3 review (high): a later transaction's BPR never dates the first claim."""
    first = era(gs04="", bpr16="20261015")
    second = (
        "ST*835*0002~BPR*I*0*C*NON************20261130~TRN*1*99*1512345678~"
        "DTM*405*20261129~N1*PR*ACME HEALTH PLAN~CLP*PCN-0002*4*100*0**12*CLAIM-88*11*1~"
        "SE*6*0002~"
    )
    batch = first.replace("GE*1*1~", second + "GE*2*1~")
    reading, others = parse_835(batch)
    assert (reading.claim_id, reading.denial_date, others) == ("CLAIM-77", "2026-10-15", 1)
    empty_first = (
        "ST*835*0003~BPR*I*0*C*NON************20261201~DTM*405*20261201~TRN*1*1*1~SE*4*0003~"
    )
    led = era(gs04="", bpr16="20261015").replace("ST*835*0001~", empty_first + "ST*835*0001~")
    assert parse_835(led)[0].denial_date == "2026-10-15", "a transaction without claims is skipped"


def test_us_6_3_extraction_prompt_asks_for_the_denial_date() -> None:
    assert "denial_date (the date of the payer's decision" in EXTRACTION_TEMPLATE.instructions


async def test_us_6_3_older_extraction_loads(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await extracted_case(desktop)
    store = service.user_store("default")
    stored = CaseService.extraction(store, case_id)
    assert stored is not None
    old = stored.model_dump(mode="json")
    del old["denial_date"]
    item = CaseItem(
        case_id=case_id,
        item_id=EXTRACTION_ITEM,
        kind="extraction",
        created_at=utc_now(),
        payload=CaseExtraction.model_validate(old)
        .model_dump_json(exclude={"denial_date"})
        .encode(),
    )
    store.put_case_item(item, audit=AuditAction.CASE_EXTRACTED)

    case = await open_case(desktop, case_id)
    assert case.extraction is not None
    assert case.extraction.denial_date.status is FieldStatus.UNREADABLE
    assert case.needs_confirmation == ["denial_date"]


async def test_us_6_3_denial_date_confirmable(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    await service.import_bundle(ACME_RULES)
    case_id = await extracted_case(desktop)
    fields = f"{PREFIX}/cases/{case_id}/fields"
    # US-6.3 review: only YYYY-MM-DD; a pasted number is not read as a Unix timestamp.
    for value in ("15/10/2026", "1760486400", "2026-10-15T00:00:00", "2026-1-5"):
        refused = await desktop.post(fields, json={"path": "denial_date", "value": value})
        assert_envelope(refused, 422, "invalid_request")
    assert read_value("service_date", 1760486400)["status"] == "unreadable"
    assert read_value("service_date", " 2026-09-01 ")["value"] == "2026-09-01"
    far = await desktop.post(fields, json={"path": "denial_date", "value": "9999-12-31"})
    assert far.status_code == 200, "stored as typed, then refused as a clock start"
    far_case = Case.model_validate_json(far.content)
    assert far_case.deadline is not None
    assert (far_case.deadline.status, far_case.deadline.due) == ("implausible_denial_date", None)
    response = await desktop.post(fields, json={"path": "denial_date", "value": "2026-10-16"})
    assert response.status_code == 200, response.text
    extraction = Case.model_validate_json(response.content).extraction
    assert extraction is not None
    assert (extraction.denial_date.value, extraction.denial_date.status) == (
        date(2026, 10, 16),
        FieldStatus.CONFIRMED,
    )
    await run_job(desktop, case_id, "process")
    again = (await open_case(desktop, case_id)).extraction
    assert again is not None
    assert again.denial_date.value == date(2026, 10, 16), "a re-run keeps the confirmed date"


# --- Rule cards: the appeal limit (corpus-import) -------------------------------------------------


async def test_us_6_3_appeal_limit_round_trip(service: CorpusService) -> None:
    await service.import_bundle(ACME_RULES)
    stored = {
        document.metadata["key"]: document
        for document in service.global_store().documents(kind="rule_card")
    }
    card = rule_card_of(stored["ACME Health/appeal_levels"])
    assert card.appeal_limit_days == 180
    assert stored["ACME Health/appeal_levels"].metadata["appeal_limit_days"] == "180"
    assert "appeal_limit_days" not in stored["ACME Health/required_docs"].metadata
    for item in ACME_RULES.items:
        assert isinstance(item, RuleCard)
        assert rule_card_of(stored[item.key]) == item


async def test_us_6_3_limit_on_another_topic_refused(service: CorpusService) -> None:
    with pytest.raises(ValidationError, match="appeal_limit_days is allowed only on appeal_levels"):
        rule_card("ACME Health", "required_docs", appeal_limit_days=180)
    for days in (0, 3651, 1.5, True, "180"):  # YAML ``yes`` is not one day
        with pytest.raises(ValidationError):
            rule_card("ACME Health", "appeal_levels", appeal_limit_days=days)
    card = rule_card("ACME Health", "appeal_levels").model_dump(mode="json")
    valid = rule_card("Other Payer", "other").model_dump(mode="json")
    body = {"items": [valid, card | {"topic": "required_docs", "appeal_limit_days": 180}]}
    worker = create_app(TOKEN, corpus=service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(worker), base_url="http://worker"
    ) as client:
        response = await client.post(
            "/corpus/import", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
        )
    assert_envelope(response, 422, "invalid_request")
    assert service.global_store().documents() == []
