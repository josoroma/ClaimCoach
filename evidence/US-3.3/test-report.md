# Test Report: US-3.3 PHI Flows Bypass the Agent Transcript

Change: us-3-3-pane-rest-only
Story: US-3.3
Verdict: pass
Coverage: 2/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), run after implementation and independent review
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

Scenario 2 has two rows: the structural proof that was exercised, and the live-session check that
cannot run until the case routes exist (US-5.1).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Pane case actions use only plugin REST calls: Then plugin.js calls only ctx.rest endpoints and never host.composer, host.request, or session methods" | PASS | `test_us_3_3_pane_uses_only_plugin_rest` (node --test): `plugin.register(fakeCtx)`, the registered pane's file input picks a synthetic PDF → the `ctx.rest` requests are exactly `POST /cases`, `POST /cases/case_0001/documents` (upload with filename and content type), `GET /cases/case_0001`. `test_us_3_3_plugin_js_never_references_agent_surfaces`: `host` is not imported from the SDK and the code (comments stripped) has no `host`, `composer`, `.request(`, or `session` token, so nothing in `plugin.js` can reach them |
| 2 | "Case processing adds nothing to agent sessions: Then the agent session gains no messages or tool calls" (structural: neither the pane nor the backend can reach a session) | PASS | `test_us_3_3_case_processing_adds_nothing_to_sessions` (node --test): upload, then Process → last request `POST /cases/case_0001/process`, state `processing`, only `ctx.rest` used. `test_us_3_3_case_processing_adds_nothing_to_sessions_backend[*]` (pytest, every module of the app package, `plugin_api.py`, `__init__.py`): imports are limited to the standard library, declared dependencies, `claimcoach`, and `hermes_cli.config` / `hermes_cli.plugin_events` / `hermes_constants` / `plugins.plugin_storage`; `test_us_3_3_scan_rejects_agent_surfaces` shows `hermes_state`, `hermes_state_messages`, `hermes_cli.active_sessions`, `run_agent`, `tools` are rejected |
| 3 | "Case processing adds nothing to agent sessions: Then the agent session gains no messages or tool calls" (a live Hermes session counted before and after processing) | UNVERIFIED | Not exercised: there is no case route to call yet (US-5.1). See Notes |

## Evidence Commands

```bash
make evidence STORY=US-3.3
make test-js
```

```text
====================== 45 passed, 669 deselected in 0.42s ======================
  ✔ test_us_3_3_pane_uses_only_plugin_rest
  ✔ test_us_3_3_plugin_js_never_references_agent_surfaces
  ✔ test_us_3_3_case_processing_adds_nothing_to_sessions
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
```

Artifacts: `evidence/US-3.3/junit.xml`, `evidence/US-3.3/junit-node.xml`

## Failures

None.

## Notes

- Row 3 is UNVERIFIED: the case routes arrive with US-5.1, which should add a `hermes` test that
  counts SessionDB messages and tool calls before and after `POST /cases/{id}/process`. The fake
  `sessions` object in the node test cannot be reached by `plugin.js`, so it is not cited as proof.
- Review findings fixed: the backend scan is an allowlist (a blocklist missed Hermes'
  `hermes_state_*` modules); the file input is disabled while busy, Process cannot be sent twice,
  and late answers after unmount or a newer action are dropped.
- Known gap recorded for US-5.1 (BR-1): `ctx.rest` goes to whichever gateway Desktop is connected
  to, which may be a remote `hermes serve`. The first case route must refuse uploads unless the
  gateway is local. This story sends no document bytes to a route that exists.
