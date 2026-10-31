"""US-4.4 Retrieval Limited to Global Plus Current Case.

Scenarios: another case's chunks are never retrieved; global chunks are available to every case;
a query without a case is invalid. The other case's chunk is made the exact nearest neighbour of
the query, so only the case filter can keep it out. Rules: BR-5, BR-14.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimcoach.corpus.bundle import CorpusBundle
from claimcoach.corpus.embed import QUERY_INSTRUCTION, Reranker
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.retrieve import Retriever
from claimcoach.corpus.service import CorpusService
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import CorpusScope, RetrievalQuery
from tests.fakes.corpus import add_case_document, make_service, vectors_for
from tests.fakes.fake_model_server import FakeModelServer, fake_embedding
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
QUESTION = "Why was the claim denied and how do I appeal?"


@pytest.fixture
def service(tmp_path: Path, corpus_server: FakeModelServer) -> CorpusService:
    corpus_server.embed_overrides.clear()
    corpus_server.rerank_requests.clear()
    return make_service(tmp_path, corpus_server)


async def two_cases(service: CorpusService) -> None:
    await service.import_bundle(CorpusBundle.model_validate({"items": [CARD]}))
    store = service.user_store("default", create=True)
    add_case_document(store, "case-a", PHI_DOCUMENTS[0]["text"])
    add_case_document(store, "case-b", PHI_DOCUMENTS[1]["text"])


# --- Scenario: Another case's chunks are never retrieved ----------------------------------------


async def test_us_4_4_other_case_chunks_never_retrieved(
    service: CorpusService, corpus_server: FakeModelServer
) -> None:
    await two_cases(service)
    store = service.user_store("default", create=True)
    # Make case B's chunk the query's exact nearest neighbour.
    b_doc = store.documents("case-b")[0]
    b_chunk = store.chunks([f"{b_doc.doc_id}#0"], case_id="case-b")
    assert b_chunk
    corpus_server.embed_overrides[QUERY_INSTRUCTION + QUESTION] = fake_embedding(b_chunk[0].text)
    nearest_in_b = store.search(vectors_for([b_chunk[0].text])[0], 1, case_id="case-b")
    assert nearest_in_b[0][1] == pytest.approx(1.0)

    results = await service.retriever("default").retrieve(
        RetrievalQuery(text=QUESTION, case_id="case-a", k=50, candidates=200)
    )
    assert results
    assert {r.chunk.case_id for r in results} <= {None, "case-a"}
    assert "case-a" in {r.chunk.case_id for r in results}
    returned = "\n".join(r.chunk.text for r in results)
    assert leaked_strings(returned, PHI_DOCUMENTS[1]) == []
    # Case B's text never even reached the reranker.
    sent = "\n".join(doc for request in corpus_server.rerank_requests for doc in request.documents)
    assert leaked_strings(sent, PHI_DOCUMENTS[1]) == []


# --- Scenario: Global chunks are available to every case ----------------------------------------


@pytest.mark.parametrize("case_id", ["case-a", "case-b", "case-without-documents"])
async def test_us_4_4_global_chunks_available(service: CorpusService, case_id: str) -> None:
    await two_cases(service)
    results = await service.retriever("default").retrieve(
        RetrievalQuery(text="Aetna appeal levels", case_id=case_id)
    )
    assert results[0].chunk.doc_id == "rule_card:Aetna/appeal_levels"
    assert results[0].chunk.scope is CorpusScope.GLOBAL
    assert results[0].score == pytest.approx(1.0)
    assert {r.chunk.case_id for r in results} <= {None, case_id}


# --- Scenario: A query without a case is invalid ------------------------------------------------


def test_us_4_4_query_requires_case(service: CorpusService) -> None:
    with pytest.raises(ValidationError):
        RetrievalQuery(text=QUESTION)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        RetrievalQuery(text=QUESTION, case_id="../other")
    store = service.user_store("default", create=True)
    with pytest.raises(CorpusError):
        store.search(vectors_for(["x"])[0], 5)
    with pytest.raises(CorpusError):
        store.chunks(["case-b-src-1#0"])
    with pytest.raises(CorpusError):
        Retriever(store, service.global_store(), service.embedder, service.reranker)


# --- Ranking ------------------------------------------------------------------------------------


async def test_us_4_4_rerank_orders_and_limits(
    service: CorpusService, corpus_server: FakeModelServer
) -> None:
    await two_cases(service)
    store = service.user_store("default", create=True)
    add_case_document(store, "case-a", "Aetna appeal levels were explained by phone.", create=False)
    results = await service.retriever("default").retrieve(
        RetrievalQuery(text="Aetna appeal levels", case_id="case-a", k=2)
    )
    assert len(results) == 2
    assert results[0].score >= results[1].score
    assert corpus_server.rerank_requests[-1].query == "Aetna appeal levels"


async def test_us_4_4_empty_corpus_skips_reranker(
    service: CorpusService, corpus_server: FakeModelServer
) -> None:
    service.user_store("default", create=True).create_case("case-a")
    results = await service.retriever("default").retrieve(
        RetrievalQuery(text=QUESTION, case_id="case-a")
    )
    assert results == []
    assert corpus_server.rerank_requests == []


# --- Review regressions -------------------------------------------------------------------------


async def test_us_4_4_search_filters_by_case_in_sql(service: CorpusService) -> None:
    """Even with case B's own vector as the query, a search for case A reads only A's vectors."""
    await two_cases(service)
    store = service.user_store("default")
    b_chunk = store.chunks([f"{store.documents('case-b')[0].doc_id}#0"], case_id="case-b")[0]
    hits = store.search(vectors_for([b_chunk.text])[0], 50, case_id="case-a")
    assert hits
    assert all(chunk_id.startswith("case-a") for chunk_id, _ in hits)


class _PurgingReranker(Reranker):
    """Purges the case while the rerank call is in flight."""

    def __init__(self, inner: Reranker, store: CorpusStore, case_id: str) -> None:
        self._inner, self._store, self._case_id = inner, store, case_id

    async def scores(self, query: str, documents: Sequence[str]) -> list[float]:
        self._store.purge_case_content(self._case_id, reason="request")
        return await self._inner.scores(query, documents)


async def test_us_4_4_case_purged_during_rerank_is_not_returned(service: CorpusService) -> None:
    await two_cases(service)
    store = service.user_store("default")
    retriever = Retriever(
        service.global_store(),
        store,
        service.embedder,
        _PurgingReranker(service.reranker, store, "case-a"),
    )
    results = await retriever.retrieve(RetrievalQuery(text=QUESTION, case_id="case-a", k=50))
    assert {r.chunk.case_id for r in results} == {None}  # only the global card survives
    assert leaked_strings("\n".join(r.chunk.text for r in results), PHI_DOCUMENTS[0]) == []


def test_us_4_4_document_id_cannot_move_between_cases(service: CorpusService) -> None:
    store = service.user_store("default", create=True)
    document = add_case_document(store, "case-a", "Denied for CO-50.")
    store.create_case("case-b")
    moved = document.model_copy(update={"case_id": "case-b"})
    with pytest.raises(CorpusError, match="one case"):
        store.put_document(moved, ["Denied for CO-50."], vectors_for(["Denied for CO-50."]))
    assert [d.doc_id for d in store.documents("case-a")] == [document.doc_id]
