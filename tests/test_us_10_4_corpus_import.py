"""US-10.4 Global Corpus Import from the Settings Page (Python half).

Scenarios: a bundle is previewed before it is imported; the import runs only after confirmation;
an invalid bundle is refused. Also: an unconfirmed import, upload limits, and problem locations
that never echo file text. The page's section runs under ``node --test``
(``plugin/desktop/tests/corpus_import.test.mjs``).
Rules: ES-1, ES-4, ES-8, BR-1, BR-2, BR-14.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI

from claimcoach.api import routes
from claimcoach.api.client import IMPORT_TIMEOUT, WorkerClient
from claimcoach.corpus.bundle import (
    MAX_PREVIEW_PAYERS,
    MAX_PREVIEW_REPLACED,
    BundleError,
    BundlePreview,
    CorpusBundle,
    ImportResult,
    parse_bundle_bytes,
    preview_of,
)
from claimcoach.corpus.service import CorpusService
from claimcoach.worker.app import create_app
from tests.fakes.corpus import TOKEN, make_service
from tests.fakes.fake_model_server import FakeModelServer
from tests.test_us_4_3_global_corpus_import import TODAY, other_items, rule_card
from tests.test_us_6_1_diagnosis import PREFIX, assert_envelope


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> Iterator[CorpusService]:
    corpus = make_service(tmp_path / "hermes", corpus_server)
    yield corpus
    corpus.close()


@pytest.fixture
async def desktop(
    service: CorpusService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    """``ctx.rest`` against the gateway over a worker that has the corpus."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    worker = create_app(TOKEN, corpus=service)
    client = WorkerClient("http://worker", lambda: TOKEN, transport=httpx.ASGITransport(worker))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: client
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        yield desktop


def bundle_bytes(items: list[dict[str, Any]]) -> bytes:
    return yaml.safe_dump({"items": items}, sort_keys=False).encode()


async def preview(
    desktop: httpx.AsyncClient, data: bytes, name: str = "rules.yaml"
) -> httpx.Response:
    return await desktop.post(
        f"{PREFIX}/corpus/import/preview", files={"file": (name, data, "application/x-yaml")}
    )


async def previewed(
    desktop: httpx.AsyncClient, data: bytes, name: str = "rules.yaml"
) -> BundlePreview:
    response = await preview(desktop, data, name)
    assert response.status_code == 200, response.text
    return BundlePreview.model_validate_json(response.content)


async def import_(
    desktop: httpx.AsyncClient, data: bytes, query: str = "?confirm=true", name: str = "rules.yaml"
) -> httpx.Response:
    return await desktop.post(
        f"{PREFIX}/corpus/import{query}", files={"file": (name, data, "application/x-yaml")}
    )


def stored(service: CorpusService) -> dict[str, str]:
    return {f"{item.kind}/{item.key}": item.title for item in service.view().items}


# --- Scenario: A bundle is previewed before it is imported ---------------------------------------


async def test_us_10_4_bundle_previewed(desktop: httpx.AsyncClient, service: CorpusService) -> None:
    await service.import_bundle(CorpusBundle.model_validate({"items": [rule_card()]}))
    before = stored(service)
    items = [
        rule_card(title="Aetna timely filing, revised"),
        rule_card(payer="Cigna", topic="submission", title="Cigna mailing address"),
        *other_items(),
    ]

    answer = await previewed(desktop, bundle_bytes(items))

    assert answer.valid is True
    assert answer.problem is None
    assert answer.items == 4
    assert answer.by_kind == {"rule_card": 2, "code": 1, "letter_template": 1}
    assert answer.payers == ["Aetna", "Cigna"]
    assert answer.stale == 1, "the CARC entry was verified 200 days ago"
    assert answer.replaces == 1, "Aetna/timely_filing is already in the global corpus"
    assert answer.replaced == ["rule_card Aetna/timely_filing"], "the page names what it replaces"
    assert stored(service) == before, "a preview imports nothing"


def test_us_10_4_preview_lists_at_most_fifty_payers() -> None:
    cards = [rule_card(payer=f"Payer {n:03d}") for n in range(MAX_PREVIEW_PAYERS + 3)]
    answer = preview_of(CorpusBundle.model_validate({"items": cards}), set(), TODAY)
    assert len(answer.payers) == MAX_PREVIEW_PAYERS
    assert answer.more_payers == 3


async def test_us_10_4_preview_needs_the_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    gateway = FastAPI()
    gateway.include_router(routes.router, prefix=PREFIX)
    gateway.dependency_overrides[routes.get_worker_client] = lambda: WorkerClient(
        "http://worker", lambda: None
    )
    transport = httpx.ASGITransport(app=gateway)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as desktop:
        response = await preview(desktop, bundle_bytes([rule_card()]))
        assert_envelope(response, 503, "worker_unavailable")
        refused = await import_(desktop, bundle_bytes([rule_card()]))
        assert_envelope(refused, 503, "worker_unavailable")


# --- Scenario: The import runs only after confirmation -------------------------------------------


async def test_us_10_4_import_after_confirmation(
    desktop: httpx.AsyncClient, service: CorpusService
) -> None:
    data = bundle_bytes([rule_card(), *other_items()])
    assert (await previewed(desktop, data)).replaces == 0

    response = await import_(desktop, data)

    assert response.status_code == 200, response.text
    result = ImportResult.model_validate_json(response.content)
    assert result.imported == {"rule_card": 1, "code": 1, "letter_template": 1}
    assert set(stored(service)) == {
        "rule_card/Aetna/timely_filing",
        "code/CARC/197",
        "letter_template/medical-necessity-l1",
    }
    assert (await previewed(desktop, data)).replaces == 3, "a second import would replace them"


@pytest.mark.parametrize("query", ["", "?confirm=false", "?confirm=1", "?confirm=yes"])
async def test_us_10_4_unconfirmed_import(
    desktop: httpx.AsyncClient, service: CorpusService, query: str
) -> None:
    assert_envelope(
        await import_(desktop, bundle_bytes([rule_card()]), query), 409, "import_not_confirmed"
    )
    assert stored(service) == {}


async def test_us_10_4_import_waits_for_the_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[float | None] = []

    async def request(*_args: object, timeout: float | None = None, **_kwargs: object) -> None:
        seen.append(timeout)

    client = WorkerClient("http://worker", lambda: TOKEN)
    monkeypatch.setattr(client, "_request", request)
    await client.import_corpus(CorpusBundle.model_validate({"items": [rule_card()]}))
    assert seen == [IMPORT_TIMEOUT]


# --- Scenario: An invalid bundle is refused ------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "name", "problem"),
    [
        (bundle_bytes([rule_card(source=None)]), "rules.yaml", "items.0.rule_card.source"),
        (b"items: [unclosed", "rules.yaml", "not valid YAML or JSON"),
        (bundle_bytes([rule_card()]), "rules.csv", ".yaml, .yml, or .json"),
        (b"\xff\xfe", "rules.json", "cannot be read"),
        (b"items: []", "rules.yaml", "items: too_short"),
        (b"", "rules.yaml", "bundle file is empty"),
    ],
)
async def test_us_10_4_invalid_bundle_refused(
    desktop: httpx.AsyncClient, service: CorpusService, data: bytes, name: str, problem: str
) -> None:
    answer = await previewed(desktop, data, name)
    assert answer.valid is False
    assert answer.problem is not None
    assert problem in answer.problem
    assert (answer.items, answer.by_kind) == (0, {})
    assert_envelope(await import_(desktop, data, name=name), 422, "invalid_bundle")
    assert stored(service) == {}


async def test_us_10_4_problem_never_echoes_file_text(desktop: httpx.AsyncClient) -> None:
    extra: dict[str, Any] = {"Jane Doe MRN 0042": "x"}
    data = bundle_bytes([rule_card(**extra)])
    answer = await previewed(desktop, data)
    assert answer.problem == "invalid bundle at items.0.rule_card.…: extra_forbidden"
    assert "Jane" not in json.dumps(answer.model_dump())


async def test_us_10_4_upload_limits(
    desktop: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "MAX_BUNDLE_BYTES", 8)
    answer = await previewed(desktop, bundle_bytes([rule_card()]))
    assert answer.problem == "bundle is larger than 5 MiB"
    big = {"content-type": "multipart/form-data; boundary=b", "content-length": str(2**30)}
    response = await desktop.post(f"{PREFIX}/corpus/import/preview", content=b"x", headers=big)
    assert (
        BundlePreview.model_validate_json(response.content).problem == "bundle is larger than 5 MiB"
    )
    not_multipart = await desktop.post(f"{PREFIX}/corpus/import/preview", json={"items": []})
    assert_envelope(not_multipart, 422, "invalid_request")
    refused = await desktop.post(f"{PREFIX}/corpus/import?confirm=true", json={"items": []})
    assert_envelope(refused, 422, "invalid_request")


def test_us_10_4_bytes_parser_checks_size_and_name() -> None:
    with pytest.raises(BundleError, match="5 MiB"):
        parse_bundle_bytes(b"x" * (5 * 1024 * 1024 + 1), "rules.yaml")
    with pytest.raises(BundleError, match=r"\.yaml"):
        parse_bundle_bytes(b"items: []", None)
    bundle = parse_bundle_bytes(json.dumps({"items": [rule_card()]}).encode(), "RULES.JSON")
    assert len(bundle.items) == 1


# --- Review regressions --------------------------------------------------------------------------


def test_us_10_4_replaced_items_are_capped() -> None:
    codes = [
        {**other_items()[0], "code": f"{n}", "title": f"Code {n}"}
        for n in range(1, MAX_PREVIEW_REPLACED + 4)
    ]
    bundle = CorpusBundle.model_validate({"items": codes})
    existing = {("code", f"CARC/{n}") for n in range(1, MAX_PREVIEW_REPLACED + 4)}
    answer = preview_of(bundle, existing, TODAY)
    assert answer.replaces == MAX_PREVIEW_REPLACED + 3
    assert len(answer.replaced) == MAX_PREVIEW_REPLACED
    assert answer.replaced[0] == "code CARC/1"


async def test_us_10_4_yaml_aliases_are_refused(desktop: httpx.AsyncClient) -> None:
    """Review: one aliased string multiplied into thousands of bodies exhausted memory."""
    data = (
        b"items:\n"
        b"  - &card {kind: rule_card, payer: Aetna, topic: other, title: T, body: B,"
        b" source: S, verified_on: 2026-10-01}\n"
        b"  - *card\n"
    )
    answer = await previewed(desktop, data)
    assert answer.problem == "bundle uses YAML aliases, which ClaimCoach does not accept"
    assert_envelope(await import_(desktop, data), 422, "invalid_bundle")


async def test_us_10_4_parsing_does_not_block_the_gateway(
    desktop: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review: a 5 MiB YAML parse ran in Hermes' event loop and stalled every other request."""
    started, release = threading.Event(), threading.Event()

    def slow(data: bytes, filename: str | None) -> CorpusBundle:
        started.set()
        release.wait(5)
        return parse_bundle_bytes(data, filename)

    monkeypatch.setattr(routes, "parse_bundle_bytes", slow)
    pending = asyncio.create_task(preview(desktop, bundle_bytes([rule_card()])))
    while not started.is_set():
        await asyncio.sleep(0.01)
    other = await asyncio.wait_for(desktop.get(f"{PREFIX}/settings"), timeout=2)
    assert other.status_code == 200, "the gateway answers while a bundle is parsed"
    release.set()
    assert (await pending).status_code == 200


@pytest.mark.parametrize(
    ("items", "problem"),
    [
        ([rule_card(), rule_card()], "invalid bundle at bundle: duplicate item key in bundle"),
        (
            [rule_card(), rule_card(payer="AETNA", topic="other")],
            "invalid bundle at bundle: a payer is spelled two ways in the bundle",
        ),
        (
            [rule_card(appeal_limit_days=30)],
            "invalid bundle at items.0.rule_card: appeal_limit_days is allowed only on "
            "appeal_levels cards",
        ),
    ],
)
def test_us_10_4_whole_bundle_problems_say_why(items: list[dict[str, Any]], problem: str) -> None:
    with pytest.raises(BundleError) as caught:
        parse_bundle_bytes(bundle_bytes(items), "rules.yaml")
    assert str(caught.value) == problem


def test_us_10_4_invented_number_keys_are_not_echoed() -> None:
    extra: dict[Any, Any] = {123456789: "x"}
    with pytest.raises(BundleError) as caught:
        parse_bundle_bytes(bundle_bytes([{**other_items()[0], **extra}]), "rules.yaml")
    assert "123456789" not in str(caught.value)
    card = rule_card(topic="required_docs", required_documents=["a", "b", ""])
    with pytest.raises(BundleError, match=r"items\.0\.rule_card\.required_documents\.2"):
        parse_bundle_bytes(bundle_bytes([card]), "rules.yaml")
