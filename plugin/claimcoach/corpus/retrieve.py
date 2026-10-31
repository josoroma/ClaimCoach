"""Retrieval over the global scope plus the current case, reranked by Qwen3-Reranker-8B.

Implements: US-4.4 (``Retriever``). Rules: BR-5 (one case's PHI never reaches another case's
prompt: user-scope candidates come only from ``CorpusStore.search(..., case_id=query.case_id)``,
which filters in SQL before any vector is decrypted), BR-14.
"""

from __future__ import annotations

from claimcoach.corpus.embed import Embedder, Reranker
from claimcoach.corpus.errors import CorpusError
from claimcoach.corpus.store import CorpusStore
from claimcoach.corpus.types import Chunk, CorpusScope, RetrievalQuery, RetrievedChunk

__all__ = ["Retriever"]


class Retriever:
    """Find the passages an explanation or draft for one case may use.

    Args:
        global_store: The global scope.
        user_store: The current profile's user scope.
        embedder: Embeds the query.
        reranker: Scores the candidates.

    Raises:
        CorpusError: The stores are not one global and one user scope.
    """

    def __init__(
        self,
        global_store: CorpusStore,
        user_store: CorpusStore,
        embedder: Embedder,
        reranker: Reranker,
    ) -> None:
        """Hold the two stores and the two models."""
        if global_store.scope is not CorpusScope.GLOBAL or user_store.scope is not CorpusScope.USER:
            raise CorpusError("a retriever needs the global scope and a user scope")
        self._global = global_store
        self._user = user_store
        self._embedder = embedder
        self._reranker = reranker

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """Return up to ``query.k`` chunks from the global scope and ``query.case_id`` only.

        The nearest ``query.candidates`` chunks of each scope are merged by cosine similarity and
        reranked together; reranker ties keep the cosine order. An empty candidate set does not
        start the reranker, and case chunks purged during the rerank are dropped.

        Raises:
            IndexStaleError: An index was built with another embedding model.
            ModelUnavailableError: The embedding or rerank model failed.
        """
        vector = await self._embedder.embed_query(query.text)
        global_hits = dict(self._global.search(vector, query.candidates))
        case_hits = dict(self._user.search(vector, query.candidates, case_id=query.case_id))
        cosine = global_hits | case_hits
        candidates: list[Chunk] = sorted(
            [
                *self._global.chunks(list(global_hits)),
                *self._user.chunks(list(case_hits), case_id=query.case_id),
            ],
            key=lambda chunk: cosine[chunk.chunk_id],
            reverse=True,
        )
        if not candidates:
            return []
        scores = await self._reranker.scores(query.text, [chunk.text for chunk in candidates])
        # A purge may have run while the reranker worked: keep only case chunks that still exist.
        current = {c.chunk_id for c in self._user.chunks(list(case_hits), case_id=query.case_id)}
        ranked = sorted(
            (
                (chunk, score)
                for chunk, score in zip(candidates, scores, strict=True)
                if chunk.scope is CorpusScope.GLOBAL or chunk.chunk_id in current
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [RetrievedChunk(chunk=chunk, score=score) for chunk, score in ranked[: query.k]]
