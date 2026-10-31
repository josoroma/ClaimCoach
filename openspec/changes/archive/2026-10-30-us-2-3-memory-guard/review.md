# Review: US-2.3

Change: us-2-3-memory-guard
Reviewer: independent general-purpose agent following `.claude/agents/story-reviewer.md` (read-only, given the changed files, not the implementer's reasoning), 2026-10-30
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | A ~16 GB reranker conversion did not count against the guard; drafting 27B could start during it | `ModelManager.begin_job(exclusive=True)`: every load queues until the conversion ends; `test_us_2_4_conversion_holds_back_model_loads` |
| low | Steady requests for a blocker re-pinned it and could starve a queued large load until `model_busy` | While a server blocks a queued load, new requests for it wait; `test_us_2_3_queued_load_is_not_starved` |
| — | Rule table; admission reserving residency under the lock (concurrent large loads; Voxtral alone) | No issues found |

## Re-verification

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 260 pytest +
12 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all nine
stories, 2 gate self-tests). `pytest -m hermes` → 4 passed (the gateway, with the model routes,
loads in Hermes' Python 3.11). Live worker cycle with `make models-load` / `make worker-stop` →
no model server left behind.
