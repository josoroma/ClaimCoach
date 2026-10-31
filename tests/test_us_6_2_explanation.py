"""US-6.2 Plain-Language Explanation and Missing-Documentation Checklist (Python half).

Scenarios: explanation and root cause are shown; checklist lists missing documentation. Also:
required documents on rule cards, whole-word payer matching, the checklist built from item numbers
only, the explanation prompt, the `explaining` stage, and what a failed explanation keeps. The pane
scenarios run under ``node --test`` (``plugin/desktop/tests/case_diagnosis.test.mjs``).
Rules: ES-1, ES-4, BR-1, BR-5, BR-10, BR-14, PC-4.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api import routes
from claimcoach.api.client import WorkerClient
from claimcoach.cases.diagnosis import RuleCardRef
from claimcoach.cases.service import CaseService
from claimcoach.corpus.bundle import CorpusBundle, RuleCard
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.importer import item_document
from claimcoach.corpus.lookup import payer_rule_cards, payer_words, rule_card_of
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import split_text
from claimcoach.models.chat import DEFAULT_MODEL_ID
from claimcoach.models.types import ModelRole
from claimcoach.pipeline.explain import (
    EXPLANATION_TEMPLATE,
    checklist_from,
    parse_explanation,
    required_documents,
)
from claimcoach.prompts.builder import registered_templates
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, corpus_client, make_service, vectors_for
from tests.fakes.diagnosis import (
    ACME_DOCUMENTS,
    CODE_BUNDLE,
    EXPLANATION,
    RULE_BUNDLE,
    classification_reply,
    explanation_reply,
    role_models,
    rule_card,
)
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_4_3_global_corpus_import import run_cli
from tests.test_us_5_1_case_intake import ERA_835
from tests.test_us_6_1_diagnosis import (
    PREFIX,
    Sent,
    assert_envelope,
    events_of,
    extracted_case,
    new_case,
    open_case,
    run_job,
)


@pytest.fixture(scope="module")
def classifier() -> Iterator[FakeModelServer]:
    """A fake Qwen3-8B (the ``classification`` role)."""
    with FakeModelServer() as server:
        yield server


@pytest.fixture(scope="module")
def explainer() -> Iterator[FakeModelServer]:
    """A fake Qwen3-14B (the ``explanation`` role)."""
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
def roles(classifier: FakeModelServer, explainer: FakeModelServer) -> dict[ModelRole, str]:
    return {
        ModelRole.CLASSIFICATION: classifier.base_url,
        ModelRole.EXPLANATION: explainer.base_url,
    }


@pytest.fixture
def sent() -> Sent:
    return []


Desktop = Callable[..., AbstractAsyncContextManager[httpx.AsyncClient]]


@pytest.fixture
def desktop_for(
    service: CorpusService,
    roles: dict[ModelRole, str],
    sent: Sent,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Desktop:
    """``ctx.rest`` against a gateway whose worker serves ``roles`` (all of them by default)."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))

    @asynccontextmanager
    async def connect(
        only: tuple[ModelRole, ...] | None = None,
    ) -> AsyncIterator[httpx.AsyncClient]:
        served = roles if only is None else {role: roles[role] for role in only}
        worker = create_app(TOKEN, corpus=service, pipeline_models=role_models(served))
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

    return connect


@pytest.fixture
async def desktop(desktop_for: Desktop) -> AsyncIterator[httpx.AsyncClient]:
    async with desktop_for() as client:
        yield client


async def diagnosed_case(
    desktop: httpx.AsyncClient, service: CorpusService, bundle: CorpusBundle | None = RULE_BUNDLE
) -> str:
    """Import the code notes and ``bundle``, then extract and diagnose the synthetic case."""
    await service.import_bundle(CODE_BUNDLE)
    if bundle is not None:
        await service.import_bundle(bundle)
    case_id = await extracted_case(desktop)
    await run_job(desktop, case_id, "diagnose")
    return case_id


# --- Scenario: Explanation and root cause are shown ----------------------------------------------


async def test_us_6_2_explanation_and_root_cause_shown(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed_case(desktop, service)

    case = await open_case(desktop, case_id)
    assert case.diagnosis is not None
    explanation = case.diagnosis.explanation
    assert explanation is not None
    assert explanation.explanation == EXPLANATION["explanation"]
    assert explanation.root_cause == EXPLANATION["root_cause"]
    assert case.diagnosis.denial_reason == "prior_authorization", "the classification is kept"


# --- Scenario: Checklist lists missing documentation ---------------------------------------------


async def test_us_6_2_checklist_lists_missing_docs(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    case_id = await diagnosed_case(desktop, service)

    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    checklist = diagnosis.checklist
    assert {item.document for item in checklist} <= set(ACME_DOCUMENTS)
    # The model chose items 3 and 1; the card's order and wording are kept.
    assert [(item.document, item.why) for item in checklist] == [
        (ACME_DOCUMENTS[0], "The appeal must cite the denial."),
        (ACME_DOCUMENTS[2], "Shows the visit was medically necessary."),
    ]
    today = date.today()
    assert diagnosis.rule_cards == [
        RuleCardRef(
            key=f"ACME Health/{topic}",
            payer="ACME Health",
            topic=topic,
            source="ACME Health provider manual (synthetic)",
            verified_on=today - timedelta(days=30),
            stale=False,
        )
        for topic in ("appeal_levels", "required_docs")
    ]


# --- Scenario: The model names a document that is not on the card --------------------------------


async def test_us_6_2_items_off_the_card_dropped(
    desktop: httpx.AsyncClient, service: CorpusService, explainer: FakeModelServer
) -> None:
    explainer.replies[DEFAULT_MODEL_ID] = explanation_reply(
        checklist=[
            {"item": 9, "why": "Off the list."},
            {"item": 0},
            {"item": 2, "why": "  Needed for a retro-authorization.  "},
            {"item": 2, "why": "A repeat."},
            {"item": "3"},
            {"item": True},
            {"document": "An invented form"},
            "junk",
            {"item": 4, "why": " "},
            {"item": 1, "why": 5},
        ]
    )
    case_id = await diagnosed_case(desktop, service)

    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert [(item.document, item.why) for item in diagnosis.checklist] == [
        (ACME_DOCUMENTS[0], None),
        (ACME_DOCUMENTS[1], "Needed for a retro-authorization."),
        (ACME_DOCUMENTS[3], None),
    ], "a reason that is not text is no reason; the item stays"


@pytest.mark.parametrize("checklist", [[], [{"item": 99}], None, "none"])
async def test_us_6_2_no_valid_item_lists_every_document(
    desktop: httpx.AsyncClient,
    service: CorpusService,
    explainer: FakeModelServer,
    checklist: object,
) -> None:
    explainer.replies[DEFAULT_MODEL_ID] = explanation_reply(checklist=checklist)
    case_id = await diagnosed_case(desktop, service)
    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert [(item.document, item.why) for item in diagnosis.checklist] == [
        (document, None) for document in ACME_DOCUMENTS
    ], "a payer requirement is never hidden because the model chose nothing"


def test_us_6_2_long_text_is_clipped_not_refused() -> None:
    """US-6.1 review: a retry at temperature 0 repeats the text, so refusing it refuses forever."""
    reply = parse_explanation(
        explanation_reply(
            explanation="word " * 500,
            root_cause="cause " * 100,
            checklist=[{"item": 1, "why": "why " * 100}],
        )
    )
    assert reply is not None
    assert (len(reply.explanation), len(reply.root_cause)) == (2000, 500)
    assert reply.checklist[0].why is not None
    assert len(reply.checklist[0].why) == 300


def test_us_6_2_checklist_from_item_numbers() -> None:
    reply = parse_explanation(explanation_reply(checklist=[{"item": 2}, {"item": 1, "why": "x"}]))
    assert reply is not None
    assert [item.document for item in checklist_from(reply.checklist, ["a", "b"])] == ["a", "b"]
    assert checklist_from(reply.checklist, []) == [], "no card list: no checklist"


# --- Scenario: No rule card for the payer --------------------------------------------------------


async def test_us_6_2_no_rule_card_for_payer(
    desktop: httpx.AsyncClient, service: CorpusService, explainer: FakeModelServer
) -> None:
    other = CorpusBundle(
        items=[rule_card("Other Payer", "required_docs", required_documents=["x"])]
    )
    case_id = await diagnosed_case(desktop, service, other)

    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert diagnosis.explanation is not None
    assert (diagnosis.checklist, diagnosis.rule_cards) == ([], [])
    data = str(explainer.requests[-1].messages[1].content)
    assert "No rule card is on file for this payer." in data
    assert "No required documents are listed for this payer." in data


async def test_us_6_2_unreadable_payer_matches_no_card(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    await service.import_bundle(RULE_BUNDLE)
    case_id = await new_case(desktop, ERA_835.replace("N1*PR*ACME HEALTH PLAN~", ""))
    await run_job(desktop, case_id, "process")
    await run_job(desktop, case_id, "diagnose")
    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert (diagnosis.checklist, diagnosis.rule_cards) == ([], [])


# --- Payer matching and the stored card -----------------------------------------------------------


async def test_us_6_2_payer_cards_match_by_whole_words(
    service: CorpusService, caplog: pytest.LogCaptureFixture
) -> None:
    await service.import_bundle(
        CorpusBundle(
            items=[
                *RULE_BUNDLE.items,
                rule_card("Health Net", "required_docs", required_documents=["Net form"]),
                rule_card("Medicare", "required_docs", required_documents=["Medicare form"]),
                rule_card("...", "other"),
            ]
        )
    )
    store = service.global_store()
    # A card stored without its payer (only possible by editing the database) is skipped.
    broken = item_document(rule_card("Broken", "other")).model_copy(
        update={"doc_id": "rule_card:Broken/other", "metadata": {"key": "Broken/other"}}
    )
    store.put_document(broken, split_text(broken.text), vectors_for(split_text(broken.text)))

    def payers(name: str | None) -> list[str]:
        return [card.key for card in payer_rule_cards(store, name)]

    acme = ["ACME Health/appeal_levels", "ACME Health/required_docs"]
    assert payers("ACME HEALTH PLAN") == acme, "the longest whole-word match wins"
    assert payers("acme-health, inc.") == acme, "case and punctuation do not matter"
    assert payers("The ACME Health Plan") == acme, "a leading article is ignored"
    assert payers("ACME") == ["ACME/required_docs"]
    assert payers("ACME HEALTH NET") == acme, "the card payer must begin the name"
    assert payers("ACMEHEALTH PLAN") == [], "words, not substrings"
    # US-6.2 review: a carded payer's name inside another payer's name is not that payer.
    assert payers("AETNA MEDICARE ADVANTAGE") == []
    assert payers("AMBETTER FROM HEALTH NET") == []
    assert payers("Health Net of California") == ["Health Net/required_docs"]
    assert payers("Other Payer Inc.") == ["Other Payer/required_docs"]
    assert payers(None) == []
    assert payers("") == []
    assert "a stored rule card did not validate: KeyError" in caplog.text
    assert payer_words("Blue Cross & Blue Shield") == ("blue", "cross", "blue", "shield")
    CaseService(service).create("default")
    with pytest.raises(CorpusError):
        payer_rule_cards(service.user_store("default"), "ACME")


async def test_us_6_2_two_spellings_are_one_payer(service: CorpusService) -> None:
    """US-6.2 review: separate imports can spell a payer two ways; one card per topic is kept."""
    today = date.today()
    await service.import_bundle(
        CorpusBundle(
            items=[
                *(
                    rule_card("Aetna", topic, verified_on=today - timedelta(days=5))
                    for topic in ("timely_filing", "appeal_levels", "submission", "other")
                ),
                rule_card(
                    "Aetna",
                    "required_docs",
                    required_documents=["Fresh form"],
                    verified_on=today - timedelta(days=5),
                ),
            ]
        )
    )
    await service.import_bundle(
        CorpusBundle(
            items=[
                rule_card(
                    "AETNA",
                    "required_docs",
                    required_documents=["Old form"],
                    verified_on=today - timedelta(days=400),
                ),
                rule_card("AETNA", "other", verified_on=today - timedelta(days=1)),
            ]
        )
    )
    cards = payer_rule_cards(service.global_store(), "AETNA LIFE INSURANCE CO")
    assert [card.key for card in cards] == [
        "Aetna/timely_filing",
        "Aetna/appeal_levels",
        "Aetna/required_docs",
        "Aetna/submission",
        "AETNA/other",
    ], "one card per topic, the most recently verified spelling, at most five"
    assert required_documents(cards) == ["Fresh form"]


async def test_us_6_2_two_spellings_in_one_bundle_refused() -> None:
    with pytest.raises(ValidationError, match="a payer is spelled two ways in the bundle"):
        CorpusBundle(items=[rule_card("Aetna", "other"), rule_card("AETNA", "submission")])
    same = CorpusBundle(items=[rule_card("Aetna", "other"), rule_card("Aetna", "submission")])
    assert len(same.items) == 2


def test_us_6_2_required_documents_count_toward_the_size_cap() -> None:
    long = ["x" * 200] * 30
    cards = [
        rule_card(f"Payer {n}", "required_docs", body="b" * 170_000, required_documents=long)
        for n in range(30)
    ]
    with pytest.raises(ValidationError, match="larger than 5 MiB"):
        CorpusBundle(items=[*cards])
    assert sum(len(card.body) + len(card.title) for card in cards) < 5 * 1024 * 1024


async def test_us_6_2_required_documents_round_trip(service: CorpusService) -> None:
    await service.import_bundle(RULE_BUNDLE)
    stored = {
        document.metadata["key"]: document
        for document in service.global_store().documents(kind="rule_card")
    }
    for card in RULE_BUNDLE.items:
        assert isinstance(card, RuleCard)
        assert rule_card_of(stored[card.key]) == card
    assert json.loads(stored["ACME Health/required_docs"].metadata["required_documents"]) == list(
        ACME_DOCUMENTS
    )
    assert "required_documents" not in stored["ACME Health/appeal_levels"].metadata
    assert required_documents([]) == []


async def test_us_6_2_list_on_another_topic_refused(service: CorpusService) -> None:
    with pytest.raises(
        ValidationError, match="required_documents is allowed only on required_docs cards"
    ):
        rule_card("ACME Health", "timely_filing", required_documents=["A form"])
    card = rule_card("ACME Health", "required_docs").model_dump(mode="json")
    valid = rule_card("Other Payer", "other").model_dump(mode="json")
    invalid = card | {"topic": "timely_filing", "required_documents": ["A form"]}
    body = {"items": [valid, invalid]}
    worker = create_app(TOKEN, corpus=service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(worker), base_url="http://worker"
    ) as client:
        response = await client.post(
            "/corpus/import", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
        )
    assert_envelope(response, 422, "invalid_request")
    assert service.global_store().documents() == [], "the valid card is not stored either"
    too_many = {"items": [card | {"required_documents": [f"Form {n}" for n in range(31)]}]}
    with pytest.raises(ValidationError):
        CorpusBundle.model_validate(too_many)


# --- The explanation prompt (BR-5, BR-10) ---------------------------------------------------------


async def test_us_6_2_prompt_carries_cards_and_numbered_documents(
    desktop: httpx.AsyncClient, service: CorpusService, explainer: FakeModelServer
) -> None:
    await diagnosed_case(desktop, service)

    assert EXPLANATION_TEMPLATE in registered_templates()
    (request,) = explainer.requests
    system, user = request.messages
    assert isinstance(system.content, str)
    assert isinstance(user.content, str)
    assert system.content.startswith(EXPLANATION_TEMPLATE.system)
    assert user.content.startswith(EXPLANATION_TEMPLATE.instructions)
    data = user.content[len(EXPLANATION_TEMPLATE.instructions) :]
    for label in ("case_facts", "classification", "code_notes", "rule_cards", "required_documents"):
        assert f"label={label}>>>" in data
    for number, document in enumerate(ACME_DOCUMENTS, 1):
        assert f"{number}. {document}" in data
    assert "ACME Health/appeal_levels (source: ACME Health provider manual (synthetic)" in data
    assert '"denial_reason": "prior_authorization"' in data
    assert "CARC/197: Precertification absent" in data
    for withheld in ("CLAIM-77", "2026-09-01", "Wrong card", "Another payer's form", "PATIENT"):
        assert withheld not in data
    extra = request.model_extra or {}
    assert (extra["temperature"], extra["max_tokens"]) == (0.0, 1536)


@pytest.mark.parametrize(
    "content",
    [
        "no json",
        explanation_reply(explanation="   "),
        explanation_reply(root_cause=None),
        json.dumps({"explanation": "Only half."}),
    ],
)
def test_us_6_2_unusable_explanations_are_refused(content: str) -> None:
    assert parse_explanation(content) is None


# --- The explaining stage -------------------------------------------------------------------------


async def test_us_6_2_progress_relayed(
    desktop: httpx.AsyncClient, service: CorpusService, sent: Sent
) -> None:
    await service.import_bundle(RULE_BUNDLE)
    case_id = await extracted_case(desktop)
    started = await run_job(desktop, case_id, "diagnose")

    events = events_of(sent, started.job_id)
    assert [(e.stage, e.progress) for e in events] == [
        ("classifying", 0.0),
        ("explaining", 0.5),
        ("done", 1.0),
    ]
    wire = json.dumps([payload for _, _, payload in sent])
    for text in ("authorization", "Medical records", "ACME"):
        assert text not in wire, "events carry no explanation, checklist, or payer"


async def test_us_6_2_missing_explanation_model_keeps_classification(
    desktop_for: Desktop, service: CorpusService, sent: Sent
) -> None:
    await service.import_bundle(RULE_BUNDLE)
    async with desktop_for((ModelRole.CLASSIFICATION,)) as desktop:
        case_id = await extracted_case(desktop)
        started = await run_job(desktop, case_id, "diagnose")
        events = events_of(sent, started.job_id)
        assert [(e.stage, e.error_code) for e in events] == [
            ("classifying", None),
            ("explaining", None),
            ("failed", "model_unavailable"),
        ]
        diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert diagnosis.denial_reason == "prior_authorization"
    assert (diagnosis.explanation, diagnosis.checklist) == (None, [])
    assert [ref.key for ref in diagnosis.rule_cards] == [
        "ACME Health/appeal_levels",
        "ACME Health/required_docs",
    ]


async def test_us_6_2_bad_explanation_reply_keeps_classification(
    desktop: httpx.AsyncClient, explainer: FakeModelServer, sent: Sent
) -> None:
    explainer.replies[DEFAULT_MODEL_ID] = "The denial is about authorization."
    case_id = await extracted_case(desktop)
    started = await run_job(desktop, case_id, "diagnose")
    assert (events_of(sent, started.job_id)[-1].error_code) == "diagnosis_failed"
    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert diagnosis.explanation is None


async def test_us_6_2_stale_card_is_flagged(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    old = date.today() - timedelta(days=200)
    stale = CorpusBundle(
        items=[
            rule_card("ACME Health", "required_docs", required_documents=["Form"], verified_on=old)
        ]
    )
    case_id = await diagnosed_case(desktop, service, stale)
    diagnosis = (await open_case(desktop, case_id)).diagnosis
    assert diagnosis is not None
    assert [(ref.key, ref.stale) for ref in diagnosis.rule_cards] == [
        ("ACME Health/required_docs", True)
    ]


# --- Real model -----------------------------------------------------------------------------------


@pytest.mark.models
async def test_us_6_2_explanation_real_model(
    tmp_path: Path, corpus_server: FakeModelServer
) -> None:
    """Qwen3-14B from MODELS_HOME explains the synthetic case (skips without its weights)."""
    from claimcoach.models.manager import ModelManager  # noqa: PLC0415
    from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home  # noqa: PLC0415
    from claimcoach.pipeline.diagnose import Diagnosis  # noqa: PLC0415
    from claimcoach.pipeline.explain import explain  # noqa: PLC0415
    from tests.test_us_6_1_diagnosis import extracted_by_service  # noqa: PLC0415

    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.EXPLANATION]
    if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
        pytest.skip(f"Qwen3-14B weights not found at {spec.model_path(home)}")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    corpus = make_service(tmp_path / "hermes", corpus_server)
    cases = CaseService(corpus)
    card = rule_card("ACME Health", "required_docs", required_documents=list(ACME_DOCUMENTS))
    try:
        case_id = await extracted_by_service(cases)
        extraction = cases.extraction_of("default", case_id)
        diagnosis = Diagnosis.model_validate(
            {
                "denial_reason": "prior_authorization",
                "appeal_likelihood": "high",
                "likelihood_reasons": ["CO-197: no authorization on file."],
                "extraction_digest": extraction.digest(),
                "diagnosed_at": "2026-10-31T12:00:00Z",
            }
        )
        async with manager.use(ModelRole.EXPLANATION) as endpoint:
            explanation, checklist = await explain(endpoint, extraction, diagnosis, [], [card])
    finally:
        await manager.shutdown()
        corpus.close()
    assert explanation.explanation
    assert explanation.root_cause
    assert {item.document for item in checklist} <= set(ACME_DOCUMENTS)
    # The fallback lists every document without a reason; a reason proves the model chose.
    assert any(item.why for item in checklist), "the model's checklist entries were read"


@pytest.mark.models
async def test_us_6_2_diagnosis_real_models(tmp_path: Path, corpus_server: FakeModelServer) -> None:
    """Qwen3-8B then Qwen3-14B through ``ModelManager`` and the memory guard (skips without
    either model's weights): the whole diagnosis job, end to end (US-6.2 review)."""
    from claimcoach.models.manager import ModelManager  # noqa: PLC0415
    from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home  # noqa: PLC0415
    from claimcoach.pipeline.diagnose import Diagnoser  # noqa: PLC0415
    from tests.test_us_6_1_diagnosis import extracted_by_service  # noqa: PLC0415

    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    for role in (ModelRole.CLASSIFICATION, ModelRole.EXPLANATION):
        spec = registry.roles[role]
        if spec.weights(home) == "missing" or not os.access(home, os.R_OK):
            pytest.skip(f"{role.value} weights not found at {spec.model_path(home)}")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "models")
    corpus = make_service(tmp_path / "hermes", corpus_server)
    cases = CaseService(corpus)
    stages: list[str] = []
    try:
        await corpus.import_bundle(RULE_BUNDLE)
        case_id = await extracted_by_service(cases)
        diagnosis = await Diagnoser(cases, manager.use).run(
            "default", case_id, lambda stage, _progress: stages.append(stage)
        )
    finally:
        await manager.shutdown()
        corpus.close()
    assert stages == ["classifying", "explaining", "done"]
    assert diagnosis.explanation is not None
    assert {item.document for item in diagnosis.checklist} <= set(ACME_DOCUMENTS)
    assert any(item.why for item in diagnosis.checklist)


def test_us_6_2_corpus_list_shows_required_documents(service: CorpusService) -> None:
    """US-6.2 review: the manager sees what a checklist will hold without diagnosing a case."""
    asyncio.run(service.import_bundle(RULE_BUNDLE))
    view = {item.key: item for item in service.view().items}
    assert view["ACME Health/required_docs"].required_documents == len(ACME_DOCUMENTS)
    assert view["ACME Health/appeal_levels"].required_documents == 0
    with corpus_client(service) as (client, _):
        code, lines = run_cli(client, "corpus", "list")
    assert code == 0
    line = next(line for line in lines if "ACME Health/required_docs" in line)
    assert line.endswith("(4 required documents)")
    plain = next(line for line in lines if "ACME Health/appeal_levels" in line)
    assert plain.endswith("(synthetic)"), "no details, no parentheses"
