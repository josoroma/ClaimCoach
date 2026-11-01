"""US-4.4 Retrieval Limited to Global Plus Current Case (the index search).

Scenarios: another case's chunks are never retrieved; global chunks are available to every case;
a search without a case is refused in the user scope. US-14.1 removed the reranking ``Retriever``
nothing called; the guarantee lives in ``CorpusStore.search`` and ``CorpusStore.chunks``, which
filter by case in SQL before any vector or chunk is decrypted, so these tests exercise them
directly. The other case's chunk is made the exact nearest neighbour of the query, so only the
case filter can keep it out. Rules: BR-5, BR-14.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claimcoach.corpus.bundle import CorpusBundle
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.types import CorpusScope
from tests.fakes.corpus import add_case_document, make_service, vectors_for
from tests.fakes.fake_model_server import FakeModelServer
from tests.fakes.phi import PHI_DOCUMENTS, leaked_strings

CARD = {
    "kind": "rule_card",
    "payer": "Aetna",
    "topic": "appeal_levels",
    "title": "Aetna appeal levels",
    "body": "Aetna allows two appeal levels; the first within 180 days of the denial.",
    "source": "Aetna provider manual 2026, section 9",
    "verified_on": "2026-09-01",
}


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> CorpusService:
    corpus_server.embed_overrides.clear()
    return make_service(tmp_path, corpus_server)


async def two_cases(service: CorpusService) -> None:
    await service.import_bundle(CorpusBundle.model_validate({"items": [CARD]}))
    store = service.user_store("default", create=True)
    add_case_document(store, "case-a", PHI_DOCUMENTS[0]["text"])
    add_case_document(store, "case-b", PHI_DOCUMENTS[1]["text"])


# --- Scenario: Another case's chunks are never retrieved ----------------------------------------


async def test_us_4_4_other_case_chunks_never_retrieved(service: CorpusService) -> None:
    await two_cases(service)
    store = service.user_store("default")
    b_chunk = store.chunks([f"{store.documents('case-b')[0].doc_id}#0"], case_id="case-b")[0]
    query = vectors_for([b_chunk.text])[0]  # case B's chunk is the exact nearest neighbour
    assert store.search(query, 1, case_id="case-b")[0][1] == pytest.approx(1.0)

    hits = store.search(query, 50, case_id="case-a")
    assert hits
    assert all(chunk_id.startswith("case-a") for chunk_id, _ in hits)
    returned = store.chunks([chunk_id for chunk_id, _ in hits], case_id="case-a")
    assert {chunk.case_id for chunk in returned} == {"case-a"}
    assert leaked_strings("\n".join(chunk.text for chunk in returned), PHI_DOCUMENTS[1]) == []
    # Asking for case B's chunk by ID under case A returns nothing either.
    assert store.chunks([b_chunk.chunk_id], case_id="case-a") == []


# --- Scenario: Global chunks are available to every case ----------------------------------------


@pytest.mark.parametrize("case_id", ["case-a", "case-b", "case-without-documents"])
async def test_us_4_4_global_chunks_available(service: CorpusService, case_id: str) -> None:
    await two_cases(service)
    service.user_store("default").create_case("case-without-documents")
    card = "rule_card:Aetna/appeal_levels#0"
    hits = service.global_store().search(
        vectors_for([f"Aetna appeal levels\n\n{CARD['body']}"])[0], 5
    )
    assert hits[0][0] == card
    (chunk,) = service.global_store().chunks([card])
    assert chunk.scope is CorpusScope.GLOBAL
    assert chunk.case_id is None
    # The case's own search never returns the global card, so global and case results stay apart.
    assert card not in {
        chunk_id
        for chunk_id, _ in service.user_store("default").search(
            vectors_for(["Aetna appeal levels"])[0], 50, case_id=case_id
        )
    }


# --- Scenario: A search without a case is invalid -----------------------------------------------


def test_us_4_4_query_requires_case(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    with pytest.raises(CorpusError):
        store.search(vectors_for(["x"])[0], 5)
    with pytest.raises(CorpusError):
        store.chunks(["case-b-src-1#0"])
    with pytest.raises(CorpusError):
        service.global_store().search(vectors_for(["x"])[0], 5, case_id="case-a")


# --- Review regressions -------------------------------------------------------------------------


async def test_us_4_4_search_filters_by_case_in_sql(service: CorpusService) -> None:
    """Even with case B's own vector as the query, a search for case A reads only A's vectors."""
    await two_cases(service)
    store = service.user_store("default")
    b_chunk = store.chunks([f"{store.documents('case-b')[0].doc_id}#0"], case_id="case-b")[0]
    hits = store.search(vectors_for([b_chunk.text])[0], 50, case_id="case-a")
    assert hits
    assert all(chunk_id.startswith("case-a") for chunk_id, _ in hits)


async def test_us_4_4_other_case_is_never_decrypted(
    service: CorpusService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review finding: the case filter runs in SQL, so case B's rows are never even decrypted."""
    await two_cases(service)
    store = service.user_store("default")
    opened: list[str] = []
    unseal = store._unseal

    def spy(blob: bytes, context: str) -> bytes:
        opened.append(context)
        return unseal(blob, context)

    monkeypatch.setattr(store, "_unseal", spy)
    b_text = store.chunks([f"{store.documents('case-b')[0].doc_id}#0"], case_id="case-b")[0].text
    opened.clear()
    hits = store.search(vectors_for([b_text])[0], 50, case_id="case-a")
    store.chunks([chunk_id for chunk_id, _ in hits], case_id="case-a")
    assert opened, "case A's own rows were opened"
    assert all(":case-a:" in context for context in opened)
    assert not [context for context in opened if ":case-b:" in context]


async def test_us_4_4_purged_case_is_not_returned(service: CorpusService) -> None:
    """A case purged between the search and the chunk read returns no text."""
    await two_cases(service)
    store = service.user_store("default")
    hits = store.search(vectors_for([PHI_DOCUMENTS[0]["text"]])[0], 50, case_id="case-a")
    assert hits
    store.purge_case_content("case-a", reason="request")
    assert store.chunks([chunk_id for chunk_id, _ in hits], case_id="case-a") == []
    assert store.search(vectors_for([PHI_DOCUMENTS[0]["text"]])[0], 50, case_id="case-a") == []


def test_us_4_4_document_id_cannot_move_between_cases(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    document = add_case_document(store, "case-a", "Denied for CO-50.")
    store.create_case("case-b")
    moved = document.model_copy(update={"case_id": "case-b"})
    with pytest.raises(CorpusError, match="one case"):
        store.put_document(moved, ["Denied for CO-50."], vectors_for(["Denied for CO-50."]))
    assert [d.doc_id for d in store.documents("case-a")] == [document.doc_id]
