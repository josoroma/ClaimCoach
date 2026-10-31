# Review: US-2.1

Change: us-2-1-model-registry
Reviewer: independent general-purpose agent following `.claude/agents/story-reviewer.md` (read-only, given the changed files, not the implementer's reasoning), 2026-10-30
Verdict: pass

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| — | Registry validation (roles, ports, `{host}`/`{port}` placeholders, lexical paths, `extra="forbid"`, write-once default via link) | No issues found |
| medium | (Reported against US-2.4) "present" accepted any one shard of a sharded model | Presence now needs every shard in `model.safetensors.index.json`; `test_us_2_1_sharded_model_needs_every_shard[5]` |
| low | (Implementer, live run) `make models-* ROLE=…` interpolated `ROLE` into a shell test | `ROLE` is checked by make against the role enum before any shell runs; `test_us_2_1_makefile_roles_match_the_enum` keeps the list in sync |

## Re-verification

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 260 pytest +
12 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all nine
stories, 2 gate self-tests). `pytest -m hermes` → 4 passed (the gateway, with the model routes,
loads in Hermes' Python 3.11). Live worker cycle with `make models-load` / `make worker-stop` →
no model server left behind.
