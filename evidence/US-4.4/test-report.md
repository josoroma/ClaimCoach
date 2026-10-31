# Test Report: US-4.4 Retrieval Limited to Global Plus Current Case

Change: us-4-4-scoped-retrieval
Story: US-4.4
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Another case's chunks are never retrieved: Then no returned chunk belongs to case B" | PASS | `test_us_4_4_other_case_chunks_never_retrieved`: cases A and B are in the same user scope and hold different synthetic PHI documents. The test makes case B's chunk the query's exact nearest neighbour (cosine 1.0 within B). `retrieve(RetrievalQuery(case_id="case-a", k=50, candidates=200))` returns only global (`None`) or `case-a` chunks, at least one of them from `case-a`. No PHI string from case B appears in the results or in any document sent to the reranker. `test_us_4_4_search_filters_by_case_in_sql`: even with B's own vector as the query, a `case-a` search returns only `case-a` chunk IDs. `test_us_4_4_case_purged_during_rerank_is_not_returned`: when case A is purged mid-rerank, only the global card comes back, and no PHI from A. `test_us_4_4_document_id_cannot_move_between_cases`: re-putting A's document under case B raises `CorpusError` ("one case"). `test_us_4_4_query_requires_case`: a query with no `case_id`, or with `../other`, is refused |
| 2 | "Global chunks are available to every case: Then the rule card is eligible to be returned" | PASS | `test_us_4_4_global_chunks_available[case-a, case-b, case-without-documents]`: for each case, the top result is `rule_card:Aetna/appeal_levels`, scope `GLOBAL`, score about 1.0, and no other case's chunk is returned. Also `test_us_4_4_rerank_orders_and_limits` (k=2, scores descending, the rerank call carries the query) and `test_us_4_4_empty_corpus_skips_reranker` |

## Evidence Commands

```bash
make evidence STORY=US-4.4
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
```

```text
tests/test_us_4_4_scoped_retrieval.py ..........                         [100%]
- generated xml file: .../evidence/US-4.4/junit.xml -
====================== 10 passed, 836 deselected in 1.15s ======================

test_us_4_4_other_case_chunks_never_retrieved PASSED
test_us_4_4_global_chunks_available[case-a] PASSED
test_us_4_4_global_chunks_available[case-b] PASSED
test_us_4_4_global_chunks_available[case-without-documents] PASSED
test_us_4_4_query_requires_case PASSED
test_us_4_4_rerank_orders_and_limits PASSED
test_us_4_4_empty_corpus_skips_reranker PASSED
test_us_4_4_search_filters_by_case_in_sql PASSED
test_us_4_4_case_purged_during_rerank_is_not_returned PASSED
test_us_4_4_document_id_cannot_move_between_cases PASSED
```

Artifacts: `evidence/US-4.4/junit.xml`

## Failures

None.

## Notes

- Embedding and reranking ran against the fake OpenAI-compatible server (`/v1/embeddings`,
  `/v1/rerank`). Real Qwen3-Embedding-8B and Qwen3-Reranker-8B servers were not exercised, and
  there is no `@pytest.mark.models` test for this story. Neither scenario depends on rank quality,
  because the case filter runs in SQL before any vector is decrypted. Whether the default
  `mlx_lm.server` command serves `/v1/rerank` is still unchecked (design.md Risks).
- The revision says candidates are now merged by cosine before the rerank. The tests check the
  rerank call and the final order (`test_us_4_4_rerank_orders_and_limits`), but no test
  specifically checks the cosine merge of the two scopes' candidates.
- "Retrieval runs for an explanation on case A" was exercised by calling the `Retriever` directly.
  The explanation flow (EPIC-6/7) is not built yet. It will have to use the same
  `RetrievalQuery`, whose `case_id` is a required field.
