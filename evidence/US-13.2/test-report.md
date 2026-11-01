# Test Report: US-13.2 Developer Guide: Models, Install, Configuration, First Run, and Daily Start

Change: us-13-2-dev-guide
Story: US-13.2
Verdict: pass
Coverage: 7/7 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5 for `make validate`; no live Hermes Desktop

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Every model role is documented from the registry: Then each role is listed with its model folder, source repository, venv, port, size tier, and what ClaimCoach uses it for" | PASS | `test_us_13_2_model_roles_match_registry`: the Models table has exactly the 8 roles of `models.default.yaml`; folder, source (`repo_id` or the reranker's `source_repo_id`), venv, port, and tier equal the registry; each use is described; the reranker's source folder and `idle_timeout_s` (600 s) are named |
| 2 | "Every model role is documented from the registry: And a test fails when a role, folder, venv, or port in the guide differs from the registry" | PASS | Same test, exact equality per cell. The reviewer's mutation run confirmed a port or tier change fails it |
| 3 | "The first run is a sequence of existing make targets: Then every command in it is a make target that exists in the Makefile or a hermes command" | PASS | `test_us_13_2_first_run_uses_make_targets`: every line of every fence (any info string, indented or not) is a Makefile target with only `NAME=value` arguments; shell operators are refused (`test_us_13_2_unknown_command_refused`, 4 cases; `test_us_13_2_every_fence_is_read`). The worker-calling targets are read from the Makefile's recipes (`$(WORKER_CURL)`, `$(CORPUS_PORT)`), and `make start` comes before the first of them |
| 4 | "The first run is a sequence of existing make targets: And the section ends by checking the worker's health and the models' status" | PASS | Same test: the last two commands are `make worker-health` and `make models-status` |
| 5 | "The daily start is separate from the first run: Then it starts the worker, checks it, and stops it, with no install step" | PASS | `test_us_13_2_daily_start_has_no_install`: the fenced commands are `start`, `models-status`, `stop`; no `hermes` line; neither the fences nor the inline commands (`make models-load ROLE=drafting`) include an install, download, link, or import target |
| 6 | "Every setting and override is documented: Then each setting is listed with its default and meaning" | PASS | `test_us_13_2_settings_documented`: the Plugin settings table equals `plugin.yaml`'s `config_schema` key for key with the same defaults; the Make variables table equals the Makefile's environment block with the same defaults (`$(HOME)` shown as `~`); `models.yaml`'s `idle_timeout_s` (600), `queue_timeout_s` (900), and `large_tier_b` (14) match the registry |
| 7 | "Every setting and override is documented: And a test fails when a setting is missing from the guide" | PASS | Same test, set equality in both directions. Its first run failed on `PYTEST_MARKERS`, which led to scoping the check to the environment block |

## Evidence Commands

```bash
make evidence STORY=US-13.2
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
===================== 11 passed, 1815 deselected in 1.40s ======================
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 250.31s (0:04:10) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-13.2/junit.xml`

## Failures

None.

## Notes

- The guide's commands were checked against the Makefile, not run on a clean Mac: no model download or `plugin-install` ran (agents are denied downloads). Whether the first run works end to end on a clean Mac is UNVERIFIED beyond the order and target checks.
- Review fixes (see review.md): the worker now starts before downloads and imports; the reranker conversion waits for its download; `models_home` is documented as declared but not read; `WORKER_PORT` and the upgrade path are documented as they work.
