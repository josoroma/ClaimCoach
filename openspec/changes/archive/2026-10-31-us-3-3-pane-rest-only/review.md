# Review: US-3.3

Change: us-3-3-pane-rest-only
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-3-5-richer-agent-access-setting
Verdict: pass after fixes; one criterion recorded UNVERIFIED

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Backend import scan was a short blocklist (missed 59 `hermes_state_*` modules, `hermes_cli.active_sessions`, `tools`) | Allowlist: stdlib, declared deps, `claimcoach`, and four named Hermes modules; `test_us_3_3_scan_rejects_agent_surfaces` |
| medium | The fake `sessions` object cannot be reached by `plugin.js`, so the session check is structural only | Evidence splits the scenario: structural proof PASS, live-session count UNVERIFIED until US-5.1 adds the case routes (design Risks) |
| medium | BR-1: `ctx.rest` may reach a remote `hermes serve` gateway; no locality check | Recorded in design Risks as a requirement for US-5.1's first case route (no route that receives document bytes exists yet) |
| low | File input enabled while uploading; Process could be sent twice; late answers after unmount applied | Input disabled while busy; busy state before awaiting; latest-action and unmount guards; two node tests |
| low | SDK stub allowed `Uint8Array` upload bytes; Hermes takes `ArrayBuffer` only | Stub narrowed |

## Re-verification

`make check` → exit 0 (27 node tests, `plugin.js` 100% lines/branches/functions; `tsc --checkJs` clean).

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
