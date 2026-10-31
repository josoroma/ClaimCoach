"""US-3.1: PHI span detector with regex validators.

Rules: BR-3, BR-14, NFR-4. Offline tests use the fake OpenAI-compatible server as the PHI model
(``tests/fakes/phi.py``); ``test_us_3_1_spans_carry_category`` runs the real Qwen3-8B.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from claimcoach.api.models import ERROR_MESSAGES, ErrorEnvelope
from claimcoach.models.chat import DEFAULT_MODEL_ID, chat_completion
from claimcoach.models.manager import ModelEndpoint, ModelManager, ModelUnavailableError
from claimcoach.models.registry import DEFAULT_REGISTRY, ModelRegistry, models_home
from claimcoach.models.types import ModelRole
from claimcoach.prompts.builder import DataItem, PromptParts, build_prompt
from claimcoach.redact.detector import (
    PHI_TEMPLATE,
    PhiDetector,
    RedactionFailedError,
    chunk_text,
    parse_reply,
)
from claimcoach.redact.redactor import Redactor
from claimcoach.redact.spans import locate, merge_spans, redact
from claimcoach.redact.types import (
    MAX_TEXT_CHARS,
    PLACEHOLDERS,
    PhiCategory,
    PhiSpan,
    RedactionResult,
    RedactResponse,
)
from claimcoach.redact.validators import find_regex_spans
from claimcoach.worker.app import create_app
from tests.conftest import REPO_ROOT
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.model_env import build_model_env, fake_server_command
from tests.fakes.phi import (
    PHI_DOCUMENTS,
    fake_phi_reply,
    leaked_strings,
    seeded_strings,
    serve_phi,
    static_models,
)
from tests.fixtures.phi import generate

SEVEN = {c for c in PhiCategory if c is not PhiCategory.OTHER}
TOKEN = "t" * 43
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def phi_server() -> Iterator[FakeModelServer]:
    with FakeModelServer() as server:
        yield server


def detector_for(server: FakeModelServer, **kwargs: Any) -> PhiDetector:
    return PhiDetector(static_models(server.base_url), **kwargs)


def leaked(text: str, *documents: generate.PhiDocument) -> list[str]:
    return leaked_strings(text, *documents)


# --- Fixtures (task 2) ---


def test_us_3_1_fixtures_are_reproducible() -> None:
    assert generate.load() == generate.generate()
    for document in PHI_DOCUMENTS:
        assert set(document["phi"]) == {c.value for c in SEVEN}
        for value in seeded_strings(document):
            assert value.lower() in document["text"].lower(), (document["id"], value)
        # Fictional exchange only: no real phone number is ever seeded.
        assert "555-01" in document["phi"]["phone"][0]


# --- Scenario: Detected spans carry a category ---


@pytest.mark.models
async def test_us_3_1_spans_carry_category(tmp_path: Path) -> None:
    """The shipped ``models.yaml`` runs Qwen3-8B; every category is found and redacted."""
    registry = ModelRegistry.load(DEFAULT_REGISTRY)
    home = models_home()
    spec = registry.roles[ModelRole.PHI_DETECTION]
    if spec.weights(home) == "missing" or not spec.venv_present(home):
        pytest.skip(f"Qwen3-8B or the mlx-lm venv is not under {home}")
    manager = ModelManager(registry, models_home=home, state_dir=tmp_path / "state")
    redactor = Redactor(PhiDetector(manager.use))
    try:
        for document in PHI_DOCUMENTS[:3]:
            result = await redactor.redact_text(document["text"])
            assert {span.category for span in result.spans} >= SEVEN, document["id"]
            assert leaked(result.text, document) == [], document["id"]
    finally:
        await manager.shutdown()


@pytest.mark.parametrize("document", PHI_DOCUMENTS, ids=lambda d: d["id"])
async def test_us_3_1_spans_carry_category_with_fake_model(
    phi_server: FakeModelServer, document: generate.PhiDocument
) -> None:
    serve_phi(phi_server, fake_phi_reply(document))
    model_spans = await detector_for(phi_server).detect(document["text"])
    result = await Redactor(detector_for(phi_server)).redact_text(document["text"])

    assert all(isinstance(span, PhiSpan) for span in result.spans)
    assert {span.category for span in model_spans} == {
        PhiCategory(span["category"]) for span in document["model"]
    }
    assert {span.category for span in result.spans} == SEVEN
    for category in SEVEN:
        assert PLACEHOLDERS[category] in result.text


def test_us_3_1_regex_validators_cover_structured_categories() -> None:
    document = PHI_DOCUMENTS[0]
    found = {
        span.category: document["text"][span.start : span.end]
        for span in find_regex_spans(document["text"])
    }
    for category in ("dob", "mrn", "member_id", "ssn", "phone"):
        assert found[PhiCategory(category)] == document["phi"][category][0]


@pytest.mark.parametrize(
    ("text", "category", "value"),
    [
        ("SSN 123-45-6789 on file", PhiCategory.SSN, "123-45-6789"),
        ("ssn 123 45 6789", PhiCategory.SSN, "123 45 6789"),
        ("Social Security Number: 123456789", PhiCategory.SSN, "123456789"),
        ("call 503-555-0101 now", PhiCategory.PHONE, "503-555-0101"),
        ("call +1 (503) 555-0101", PhiCategory.PHONE, "+1 (503) 555-0101"),
        ("D.O.B. 3/4/62", PhiCategory.DOB, "3/4/62"),
        ("born on 4 Mar 1962", PhiCategory.DOB, "4 Mar 1962"),
        ("Date of Birth: Sept. 9, 1990", PhiCategory.DOB, "Sept. 9, 1990"),
        ("Medical Record Number: AB-12345", PhiCategory.MRN, "AB-12345"),
        ("Policy # ZX9876543", PhiCategory.MEMBER_ID, "ZX9876543"),
        ("Subscriber ID: H12345678", PhiCategory.MEMBER_ID, "H12345678"),
        ("member_id\n\x1e\nHJY325842560", PhiCategory.MEMBER_ID, "HJY325842560"),
        ('{"patient_member_id": "HJY325842560"}', PhiCategory.MEMBER_ID, "HJY325842560"),
        ("date_of_birth=1951-02-01", PhiCategory.DOB, "1951-02-01"),
        ("patient_account_number: 4454893", PhiCategory.MRN, "4454893"),
        ("social_security_number 322639968", PhiCategory.SSN, "322639968"),
        ("DOB: JAN 02 1960", PhiCategory.DOB, "JAN 02 1960"),
        ("DOB: JANUARY 2nd, 1960", PhiCategory.DOB, "JANUARY 2nd, 1960"),
        ("DOB - 04-MAR-1962", PhiCategory.DOB, "04-MAR-1962"),
        ("Date of Birth (MM/DD/YYYY): 01/02/1960", PhiCategory.DOB, "01/02/1960"),
        ("DOB 01021960", PhiCategory.DOB, "01021960"),
        ("ID #: 98765432", PhiCategory.MEMBER_ID, "98765432"),
        ("Mbr ID HJY325842560", PhiCategory.MEMBER_ID, "HJY325842560"),
        ("Member's ID: H1234567", PhiCategory.MEMBER_ID, "H1234567"),
        ("Member Identification Number: ABC12345", PhiCategory.MEMBER_ID, "ABC12345"),
        ("Member ID: XYZ 123456789", PhiCategory.MEMBER_ID, "XYZ 123456789"),
        ("MBI: 1EG4TE5MK73", PhiCategory.MEMBER_ID, "1EG4TE5MK73"),
        ("HICN 123456789A", PhiCategory.MEMBER_ID, "123456789A"),
        ("Patient Acct #: 445566", PhiCategory.MRN, "445566"),
        ("Pat Acct No 778899", PhiCategory.MRN, "778899"),
        ("Patient Control Number: PCN12345", PhiCategory.MRN, "PCN12345"),
        ("MR# 1234567", PhiCategory.MRN, "1234567"),
        ("SSN XXX-XX-6789", PhiCategory.SSN, "XXX-XX-6789"),
        ("SSN 123.45.6789", PhiCategory.SSN, "123.45.6789"),
        ("Phone: 5035550101", PhiCategory.PHONE, "5035550101"),
        ("call 503-555-0101 x12", PhiCategory.PHONE, "503-555-0101 x12"),
    ],
)
def test_us_3_1_validator_matches(text: str, category: PhiCategory, value: str) -> None:
    spans = [s for s in find_regex_spans(text) if s.category is category]
    assert [text[s.start : s.end] for s in spans] == [value]


@pytest.mark.parametrize(
    "text",
    [
        "Claim 4471-22 denied under CARC CO-197, RARC N290.",
        "Service date 2026-09-12, billed $180.00, CPT 99214.",
        "Member services: see the back of your card.",
        "Account for the remaining balance.",
        "Patient: Avery Vandermeer",
        "Identified the issue; idle since Monday.",
    ],
)
def test_us_3_1_validators_ignore_codes_and_unlabeled_dates(text: str) -> None:
    assert find_regex_spans(text) == []


# --- Scenario: Redacted text replaces each span ---


@pytest.mark.parametrize("document", PHI_DOCUMENTS, ids=lambda d: d["id"])
async def test_us_3_1_redacted_text_replaces_spans(
    phi_server: FakeModelServer, document: generate.PhiDocument
) -> None:
    serve_phi(phi_server, fake_phi_reply(document))
    spans = await detector_for(phi_server).detect(document["text"])
    result = redact(document["text"], spans + find_regex_spans(document["text"]))

    assert leaked(result.text, document) == []
    assert ("CO-197" in result.text) == ("CO-197" in document["text"]), "codes survive"
    assert "4471-22" in result.text, "claim numbers survive redaction"
    assert result.second_pass_hits == 0


def test_us_3_1_propagation_redacts_every_form_of_a_name() -> None:
    text = "Patient Jane Doe. Dear Ms. Doe, JANE called. Doesnt match Doer."
    result = redact(text, locate(text, "Jane Doe", PhiCategory.NAME))
    assert result.text == "Patient [NAME]. Dear Ms. [NAME], [NAME] called. Doesnt match Doer."


def test_us_3_1_second_pass_catches_what_spans_missed() -> None:
    document = PHI_DOCUMENTS[0]
    result = redact(document["text"], [])
    assert result.spans == ()
    assert result.second_pass_hits == 5
    for category in ("dob", "mrn", "member_id", "ssn", "phone"):
        assert document["phi"][category][0] not in result.text
    assert document["phi"]["name"][0] in result.text, "names need the model; regex cannot find them"


def test_us_3_1_overlapping_spans_merge_to_the_longest_category() -> None:
    spans = [
        PhiSpan(start=0, end=4, category=PhiCategory.MRN, source="regex"),
        PhiSpan(start=2, end=12, category=PhiCategory.ADDRESS, source="model"),
        PhiSpan(start=3, end=5, category=PhiCategory.PHONE, source="regex"),
        PhiSpan(start=20, end=22, category=PhiCategory.NAME, source="model"),
    ]
    assert merge_spans(spans) == [
        PhiSpan(start=0, end=12, category=PhiCategory.ADDRESS, source="model"),
        PhiSpan(start=20, end=22, category=PhiCategory.NAME, source="model"),
    ]


def test_us_3_1_types_validate() -> None:
    with pytest.raises(ValidationError, match="end after it starts"):
        PhiSpan(start=3, end=3, category=PhiCategory.NAME, source="model")
    result = RedactionResult(
        text="[NAME] [NAME]",
        spans=(
            PhiSpan(start=0, end=1, category=PhiCategory.NAME, source="model"),
            PhiSpan(start=2, end=3, category=PhiCategory.NAME, source="propagated"),
        ),
        second_pass_hits=0,
    )
    response = RedactResponse.from_result(result)
    assert response.counts == {PhiCategory.NAME: 2}
    assert "start" not in response.model_dump_json(), "responses carry no offsets or values"


# --- The model call ---


def test_us_3_1_parse_reply() -> None:
    reply = (
        "<think>The patient is Jane.</think>Sure: "
        '{"spans": [{"text": " Jane Doe ", "category": "Person"},'
        ' {"text": "x1", "category": "date-of-birth"}, {"text": "", "category": "ssn"},'
        ' {"text": "y", "category": "weird"}, {"text": "z", "category": "SSN", "extra": 1}]}'
    )
    assert parse_reply(reply) == [
        ("Jane Doe", PhiCategory.NAME),
        ("x1", PhiCategory.DOB),
        ("y", PhiCategory.OTHER),
        ("z", PhiCategory.SSN),
    ]


@pytest.mark.parametrize("reply", ["no json here", "} {", '{"spans": "nope"}', '{"text": 1}'])
def test_us_3_1_unusable_reply_fails_closed(reply: str) -> None:
    with pytest.raises(RedactionFailedError):
        parse_reply(reply)


async def test_us_3_1_detector_prompt_keeps_document_in_data_section(
    phi_server: FakeModelServer,
) -> None:
    document = PHI_DOCUMENTS[2]  # a call note with an injected instruction
    serve_phi(phi_server, fake_phi_reply(document))
    await detector_for(phi_server).detect(document["text"])
    request = phi_server.requests[-1]
    system, user = (m.content for m in request.messages)

    assert request.model == DEFAULT_MODEL_ID
    assert [m.role for m in request.messages] == ["system", "user"]
    assert "Ignore previous instructions" not in system
    assert document["phi"]["ssn"][0] not in system
    assert user.startswith(PHI_TEMPLATE.instructions)
    head, _, data = user.partition("<<<DATA ")
    assert document["text"] not in head
    assert document["text"] in data
    assert data.rstrip().endswith(">>>")


async def test_us_3_1_long_documents_are_chunked(phi_server: FakeModelServer) -> None:
    documents = PHI_DOCUMENTS[:4]
    text = "\n".join(d["text"] for d in documents)
    serve_phi(phi_server, fake_phi_reply(*documents))
    before = len(phi_server.requests)
    result = await Redactor(detector_for(phi_server, chunk_chars=500)).redact_text(text)
    assert len(phi_server.requests) - before == len(chunk_text(text, 500)) > 1
    assert leaked(result.text, *documents) == []


async def test_us_3_1_blank_text_skips_the_model(phi_server: FakeModelServer) -> None:
    before = len(phi_server.requests)
    assert await detector_for(phi_server).detect("  \n") == []
    assert len(phi_server.requests) == before


def test_us_3_1_chunk_text() -> None:
    text = "short\n" + "x" * 25 + "\nend"
    chunks = chunk_text(text, 10)
    assert "".join(chunks) == text
    assert all(len(c) <= 10 for c in chunks)
    assert chunks == ["short\n", "x" * 10, "x" * 10, "xxxxx\nend"]
    assert chunk_text("a\nb\n", 10) == ["a\nb\n"]
    assert chunk_text("", 10) == []


def mock_model(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def completion(content: str, finish_reason: str = "stop") -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


async def test_us_3_1_truncated_reply_fails_closed() -> None:
    transport = mock_model(lambda _r: httpx.Response(200, json=completion('{"spans": [', "length")))
    detector = PhiDetector(static_models("http://127.0.0.1:9/v1"), transport=transport)
    with pytest.raises(RedactionFailedError):
        await detector.detect("Patient Jane Doe")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": []}),
    ],
)
async def test_us_3_1_model_errors_are_model_unavailable(response: httpx.Response) -> None:
    prompt = build_prompt(
        PromptParts(template=PHI_TEMPLATE, data=(DataItem(label="document", text="x"),))
    )
    endpoint = ModelEndpoint(role=ModelRole.PHI_DETECTION, base_url="http://127.0.0.1:9/v1")
    with pytest.raises(ModelUnavailableError):
        await chat_completion(
            endpoint, prompt, max_tokens=8, transport=mock_model(lambda _r: response)
        )


async def test_us_3_1_unreachable_model_is_model_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    detector = PhiDetector(static_models("http://127.0.0.1:9/v1"), transport=mock_model(refuse))
    with pytest.raises(ModelUnavailableError):
        await detector.detect("Patient Jane Doe")


# --- Worker route ---


@asynccontextmanager
async def redact_worker(tmp_path: Path, reply: str) -> AsyncIterator[httpx.AsyncClient]:
    reply_file = tmp_path / "phi-reply.json"
    reply_file.write_text(reply)
    command = fake_server_command("--model", DEFAULT_MODEL_ID, "--reply-file", str(reply_file))
    shared = {"command": command}
    env = build_model_env(tmp_path, roles={"phi_detection": shared, "classification": shared})
    app: FastAPI = create_app(TOKEN, env.manager())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://w", headers=AUTH) as client,
    ):
        yield client


@pytest.fixture
def _fake_server_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))


@pytest.mark.usefixtures("_fake_server_importable")
async def test_us_3_1_worker_redact_route(tmp_path: Path) -> None:
    documents = PHI_DOCUMENTS[:3]
    text = "\n".join(d["text"] for d in documents)
    async with redact_worker(tmp_path, fake_phi_reply(*documents)) as client:
        response = await client.post("/redact", json={"text": text})
        too_long = await client.post("/redact", json={"text": "x" * (MAX_TEXT_CHARS + 1)})
    assert response.status_code == 200
    body = RedactResponse.model_validate_json(response.content)
    assert leaked(body.text, *documents) == []
    assert set(body.counts) == SEVEN
    assert too_long.status_code == 422
    assert ErrorEnvelope.model_validate_json(too_long.content).error.code == "invalid_request"


@pytest.mark.usefixtures("_fake_server_importable")
async def test_us_3_1_worker_redact_failure_is_an_envelope(tmp_path: Path) -> None:
    document = PHI_DOCUMENTS[0]
    async with redact_worker(tmp_path, "I cannot help with that.") as client:
        response = await client.post("/redact", json={"text": document["text"]})
    assert response.status_code == 503
    assert json.loads(response.content) == {
        "ok": False,
        "error": {"code": "redaction_failed", "message": ERROR_MESSAGES["redaction_failed"]},
    }


# --- Review findings (US-3.1): backtracking, layout-rewritten values, short surnames ---


@pytest.mark.parametrize("filler", [" " * 10_000, "_" * 10_000, "\n" * 10_000, " \t" * 5_000])
@pytest.mark.parametrize(
    "label", ["Member", "Patient", "DOB", "Account", "SSN", "member_id", "Phone", "ID", "MRN"]
)
def test_us_3_1_validators_resist_backtracking(label: str, filler: str) -> None:
    started = time.perf_counter()
    find_regex_spans(f"{label}{filler}x")
    assert time.perf_counter() - started < 0.5


def test_us_3_1_model_values_match_across_layout_changes() -> None:
    text = "PATIENT LI, KEANU\n12 ELM ST\nSPRINGFIELD  IL 62701\nCLAIM 4471-22"
    spans = locate(text, "12 Elm St, Springfield, IL 62701", PhiCategory.ADDRESS)
    assert [text[s.start : s.end] for s in spans] == ["12 ELM ST\nSPRINGFIELD  IL 62701"]


async def test_us_3_1_unlocatable_values_fall_back_to_their_words(
    phi_server: FakeModelServer, caplog: pytest.LogCaptureFixture
) -> None:
    text = "Patient Keanu Ashgrove of Glenhaven; claim 4471-22."
    serve_phi(
        phi_server,
        json.dumps(
            {
                "spans": [
                    {"text": "Ashgrove, Keanu (Glenhaven resident)", "category": "name"},
                    {"text": "Zed Q", "category": "name"},  # invented: nothing to find
                ]
            }
        ),
    )
    with caplog.at_level(logging.INFO, logger="claimcoach.redact"):
        result = await Redactor(detector_for(phi_server)).redact_text(text)
    assert result.text == "Patient [NAME] [NAME] of [NAME]; claim 4471-22."
    assert "1 PHI values from the model were not found in the document" in caplog.text
    assert "Zed" not in caplog.text


def test_us_3_1_two_letter_surnames_are_redacted_in_name_context() -> None:
    text = "LI, JANE called. Dear Ms. Li, thanks. The list of claims is long. Li-ion battery."
    result = redact(
        text, locate(text, "Jane Li", PhiCategory.NAME) + locate(text, "LI, JANE", PhiCategory.NAME)
    )
    assert result.text == (
        "[NAME] called. Dear Ms. [NAME], thanks. The list of claims is long. Li-ion battery."
    )


def test_us_3_1_names_of_only_short_words_use_the_title_context() -> None:
    text = "Li Ng called. Dr. Ng will reply; Ng, Li is not a match."
    result = redact(text, locate(text, "Li Ng", PhiCategory.NAME))
    assert result.text == "[NAME] called. Dr. [NAME] will reply; Ng, Li is not a match."


async def test_us_3_1_detection_has_a_total_deadline() -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=completion('{"spans": []}'))

    detector = PhiDetector(
        static_models("http://127.0.0.1:9/v1"), total_timeout=0.1, transport=mock_model(slow)
    )
    with pytest.raises(RedactionFailedError):
        await detector.detect("Patient Jane Doe")
