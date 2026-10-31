# Proposal: US-4.4 Retrieval Limited to Global Plus Current Case

## Why

BR-5: explanations and drafts retrieve from the global scope plus the current case only, so one
patient's PHI never reaches another case's prompt. The rule must hold by construction, not by a
filter a caller can forget.

## What Changes

- `claimcoach/corpus/types.py`: `RetrievalQuery` (query text, required `case_id`, `k`) and
  `RetrievedChunk`.
- `claimcoach/corpus/retrieve.py`: `Retriever` — embed the query, take the nearest global chunks
  and the nearest chunks of the query's case, rerank the union with Qwen3-Reranker-8B, return the
  top `k`.
- `claimcoach/corpus/embed.py`: `Reranker` (`/v1/rerank` on the `rerank` role).
- `CorpusStore.search()` and `chunks()` in the user scope require a `case_id` and filter in SQL;
  there is no user-scope read across cases.

## Capabilities

### New Capabilities
- `scoped-retrieval`: the retrieval rule and the rerank step.

### Modified Capabilities
- None.

## Impact

- Library only: EPIC-6 and EPIC-7 call `Retriever` inside the worker. No REST route.
