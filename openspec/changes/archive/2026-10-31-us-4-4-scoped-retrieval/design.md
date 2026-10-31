# Design: US-4.4 Retrieval Limited to Global Plus Current Case

## Context

The user scope holds every case of one biller in one database (US-4.1), so the case boundary is a
column, not a file.

## Goals / Non-Goals

**Goals:** another case's chunks are never candidates; global chunks are candidates for every
case; rerank with Qwen3-Reranker-8B.

**Non-Goals:** prompt assembly (EPIC-6/7 use `build_prompt`); hybrid keyword search.

## Decisions

1. **The case filter lives in the store, in SQL.** `CorpusStore.search(vector, n, case_id)`
   requires `case_id` in the user scope (and refuses one in the global scope); the `WHERE case_id
   = ?` runs before any vector is decrypted. `RetrievalQuery.case_id` is a required field, so a
   query without a case does not validate. *Alternative:* filter after a scope-wide search —
   rejected: it would decrypt and rank other cases' vectors, and one forgotten filter leaks PHI.
2. **Two-stage ranking.** Up to `candidates` (default 32) nearest chunks per scope by cosine, then
   one `/v1/rerank` call (Jina/Cohere-style `{query, documents}` → `results[{index,
   relevance_score}]`) over the union; ties keep cosine order.
3. **Queries use the Qwen3-Embedding instruction prefix**; documents are embedded without it.
4. **Empty candidates skip the reranker**, so an empty corpus does not start a model server.

5. **Review outcomes.** Candidates are merged by cosine before the rerank; case chunks are
   re-checked after it, so a purge in between is honoured; a document ID cannot move to another
   case.

## Risks / Trade-offs

- [The default `mlx_lm.server` command may not serve `/v1/rerank`] → same as US-4.1's embeddings:
  the role command is editable and real-model checks are `@pytest.mark.models`.
