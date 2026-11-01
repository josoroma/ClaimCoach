# Review: US-14.1

Change: us-14-1-remove-retrieval-reranker
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | No test checked that a case-A search never decrypts case B's rows; a search that decrypted every case and filtered in Python passed | `test_us_4_4_other_case_is_never_decrypted` records every `_unseal` context during a case-A search and chunk read and refuses any `:case-b:` context |
| low | `test_us_14_1_index_kept` could not fail if import stopped embedding (one chunk in the index) | It asserts the chunk text sent to the embedding server and a similarity of 1.0 for the chunk's own embedding |
| low | Tasks ticked before evidence existed | `evidence/US-14.1/` recorded before archiving |
| low | US-2.1's scenario still lists `rerank` without a supersede note | Added to US-2.1's Open Questions in SPECS.md |
| low | A hand-edited role set to `convert` now fails to load; the upgrade row said nothing was needed | The upgrade row says such a role needs a `repo_id` |
| nit | `_INSTALL_ONLY` still listed `models-convert`; the Claude Code deny rule and `end_job`'s notify remain | Removed from `_INSTALL_ONLY`; the deny rule stays as a safeguard; `end_job` still wakes waiters harmlessly |
| nit | Living spec Purpose lines may stay stale after archive | Checked after archiving |

## Re-verification

```text
$ make verify
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
