# Review: US-4.4

Change: us-4-4-scoped-retrieval
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-3-global-corpus-import
Verdict: pass after fixes (no high findings; BR-5 holds by construction)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Default `rerank` command may not serve `/v1/rerank` | Not fixed here (needs real models); follow-up proposed; evidence notes the real reranker is unverified |
| low | A `doc_id` reused in another case silently moved the document | `_put` refuses to replace a document owned by another case; `test_us_4_4_document_id_cannot_move_between_cases` |
| low | Ties kept list order (global first), not cosine order as designed | Candidates are merged by cosine similarity before the rerank |
| low | A purge during the rerank await could still return the purged chunks | Case chunks are re-checked after the rerank; `test_us_4_4_case_purged_during_rerank_is_not_returned` |
| low | Nothing asserted the SQL-level case filter directly | `test_us_4_4_search_filters_by_case_in_sql` (case B's own vector as the query, only case A's chunks) |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
