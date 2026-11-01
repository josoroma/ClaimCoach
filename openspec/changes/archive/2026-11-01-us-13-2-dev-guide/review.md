# Review: US-13.2

Change: us-13-2-dev-guide
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes (the first run on a clean Mac was checked against the Makefile, not executed)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The first run ran `models-download`, `models-convert`, and `corpus-import` before `make start`, though all three call the worker; the test pinned that order | The worker starts at step 5; the section ends with `make worker-health` and `make models-status`. The test reads the worker-calling targets from the Makefile's recipes (`$(WORKER_CURL)`, `$(CORPUS_PORT)`) and requires `start` before the first one |
| medium | `models-convert` right after the rerank download only answers `in_progress` | The guide says to wait for `source_present: true` and no `acquire`, and that the reranker is optional while no step calls retrieval |
| medium | The `models_home` setting is documented as working but nothing reads it | Documented as declared but not read; the weights folder comes from `MODELS_HOME` in the worker's environment |
| medium | `WORKER_PORT` presented as a normal override; the gateway and tools always use 18200 | Documented as such; the example now overrides `MODELS_HOME` |
| medium | "After a git pull, restart the gateway" left out the upgrade steps | Links `upgrade.md` and names its steps, including the Desktop Rescan |
| medium | `phi_detection` said to redact exports | Now: logs and agent tool results; the fine-tune export is checked with the regex validators |
| low | Rerank and embedding uses described a retrieval path no production flow calls | Both rows say what runs today (embedding at import and reindex; rerank not in a case flow); the US-13.4 user diagram was corrected the same way |
| low | `make doctor` "changes nothing"; venv check sees only Python; US-4.7 troubleshooting entry; "generated" config schema; state names; reindex profiles; `missing` column | Each corrected in the guide |
| medium (tests) | Make variable defaults were not compared; only ` ```bash ` fences were read; shell operators, `hermes` lines, and inline commands were not checked; one comment ended the env block; settings and variables tables were merged; `models.yaml` values not compared | Helpers moved to `tests/doc_checks.py`; every fence and inline span is read; shell operators and non-`NAME=value` arguments are refused; the env block must be only `?=` lines up to a blank line; each subsection's table must equal its source with the same defaults; the three `models.yaml` values are compared |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 244.06s (0:04:04) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-13.1
ok   US-13.2
ok   US-13.3
ok   US-13.4
ok   US-13.5
================ 2 passed, 1824 deselected in 248.32s (0:04:08) ================
```

The first `make verify` run failed once in its nested `make check` (the gate's self-test):
`test_us_2_2_group_members_are_stopped_with_the_leader` raised `PermissionError` from `os.killpg` in
`_group_alive` (`plugin/claimcoach/models/manager.py`, EPIC-2), which catches only
`ProcessLookupError`. It passed 5 of 5 runs alone and on the second `make verify`. This change does
not touch that code; it is reported to the user as a separate follow-up.
