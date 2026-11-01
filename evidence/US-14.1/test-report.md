# Test Report: US-14.1 Remove Unused Retrieval and the Reranker

Change: us-14-1-remove-retrieval-reranker
Story: US-14.1
Verdict: pass
Coverage: 7/7 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; no live Hermes Desktop; no real models

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The reranker is not a model role: Then it has no rerank role and no conversion recipe" | PASS | `test_us_14_1_no_rerank_role`: `ModelRole` has no `rerank`; the default `models.yaml` has no `rerank` role and `acquire` holds only `download` |
| 2 | "The reranker is not a model role: And the models status lists no rerank role" | PASS | Same test: `ModelManager.status()` over the default registry lists exactly the seven roles; `ModelStatus` has no `source_present` |
| 3 | "An existing models.yaml still loads: Then it loads without them and every other role is unchanged" | PASS | `test_us_14_1_old_registry_still_loads`: a pre-US-14.1 file (today's default plus the old `rerank` role and `acquire.convert`) loads through `load_registry` with roles and `acquire` equal to the default's. `test_us_14_1_only_the_retired_keys_are_dropped` (2 cases) and `test_us_14_1_a_non_mapping_registry_is_still_refused`: any other unknown role or command is still refused |
| 4 | "An existing models.yaml still loads: And the file is not rewritten" | PASS | Same test: the file's bytes are identical before and after loading |
| 5 | "No conversion route or command remains: Then there is no models/convert route and no models-convert target" | PASS | `test_us_14_1_no_conversion_route_or_target`: no route containing `convert` on the gateway router or the worker's model router, no `models-convert` Make target, no `rerank` in the Makefile, no `conversion_unavailable` code, no `Acquirer.convert`. `test_us_7_3_*` and `test_us_1_3_*` pin the full route sets |
| 6 | "The corpus index is kept: Then its chunks are embedded and stored in the global vector index" | PASS | `test_us_14_1_index_kept`: importing a code entry sends exactly its chunk text to the embedding server; the index records the embedding model and one vector per chunk; searching with the chunk's own embedding returns it with similarity 1.0 |
| 7 | "The corpus index is kept: And a search of a user scope still requires a case ID and returns that case's chunks only" | PASS | Same test refuses a user search without a case. The rewritten US-4.4 suite: `test_us_4_4_other_case_chunks_never_retrieved`, `test_us_4_4_search_filters_by_case_in_sql`, `test_us_4_4_other_case_is_never_decrypted` (case B's rows are never even decrypted while case A searches), `test_us_4_4_purged_case_is_not_returned` |

## Evidence Commands

```bash
make evidence STORY=US-14.1
uv run pytest -q tests/test_us_4_4_scoped_retrieval.py
make verify
```

```text
====================== 7 passed, 1819 deselected in 1.67s ======================
9 passed (US-4.4)
All checks passed!
TOTAL    8551      0   1414      0   100%
=============== 1812 passed, 14 deselected in 244.78s (0:04:04) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-14.1
ok   US-14.2
================ 2 passed, 1824 deselected in 248.85s (0:04:08) ================
```

Artifacts: `evidence/US-14.1/junit.xml`

## Failures

None.

## Notes

- Product decision 2026-11-01: remove retrieval and the reranker, keep the vector index. No real model ran; the reranker's folders on this Mac (`~/Models/Qwen3-Reranker-8B*`) were not touched.
- Review fixes (see review.md): a decrypt-context test for the kept case filter, a stronger index test, a US-2.1 supersede note in SPECS.md, and the upgrade row for a hand-converted role.
