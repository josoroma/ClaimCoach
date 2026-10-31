# ClaimCoach delivery conventions

## Layout

| What | Where |
| --- | --- |
| App package (gateway + worker) | `plugin/claimcoach/` (`api/`, `worker/`, `models/`, …) |
| Gateway entry point | `plugin/dashboard/plugin_api.py` → `claimcoach.api.routes.router` |
| Worker routes | `claimcoach.worker.app.create_app()` includes routers; bearer middleware covers all |
| Tests | `tests/test_us_<epic>_<n>_<topic>.py`; fakes in `tests/fakes/` |
| Evidence | `evidence/US-x.y/{test-report.md,junit.xml}` |
| Runbooks | `docs/runbooks/*.md` with Preconditions / Steps / Verification / Rollback |
| ADRs | `docs/adr/NNNN-*.md` |

## OpenSpec change files

- `proposal.md`: `# Proposal: US-x.y <title>` → `## Why`, `## What Changes`, `## Capabilities`
  (`### New Capabilities` / `### Modified Capabilities`), `## Impact`.
- `design.md`: `# Design: …` → `## Context`, `## Goals / Non-Goals`, `## Decisions` (numbered,
  each with the rejected alternative), `## Risks / Trade-offs` (`[risk] → mitigation`).
- `specs/<capability>/spec.md`: `# Spec Delta`, `## Purpose`, `## ADDED Requirements`, each
  `### Requirement:` uses SHALL and has at least one `#### Scenario:` with `- **WHEN**` /
  `- **THEN**` / `- **AND**`.
- `tasks.md`: `## n. Group` → `- [ ] n.m <task>; verify <test or command>`.
- `review.md`: `Change:`, `Reviewer:`, `Verdict:`, `## Findings and resolution` table,
  `## Re-verification`.

## Rule IDs worth citing

BR-1 downloads only after confirmation · BR-11 `MODELS_HOME`, ports 18200–18219, no copied
weights · BR-12 memory guard · BR-13 state outside the install dir · BR-14 PHI-free logs and
responses · ES-1 typing · ES-3 docstrings · ES-4 tests · ES-5 evidence · ES-6 runbooks ·
ES-8 envelope · PC-4 gateway only proxies.

## Review checklist (what EPIC-1 reviews caught)

- Loopback httpx clients set `trust_env=False` (proxies would see tokens).
- A PID file is trusted only after checking the process command line.
- Exception text never reaches logs or responses; FastAPI's 422 echoes input unless enveloped.
- Every wait is bounded; SIGTERM escalates to SIGKILL; temp state is removed on failure.
- State lives under `app_data_dir()` / `plugin_data_dir()`, never in the install dir.
