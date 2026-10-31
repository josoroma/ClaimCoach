# Review: US-3.5

Change: us-3-5-richer-agent-access-setting
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-3-3-pane-rest-only
Verdict: pass after fixes; scope still needs Product Manager sign-off

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Statusbar read `/settings` once per mount; a change in Settings stayed stale | Re-read every 15 s (timer cleared on unmount); `test_us_3_5_statusbar_follows_a_changed_setting` |
| low | Lax bool: `"yes"`, `"1"`, `1` read as on | `StrictBool`; three new off cases in `test_us_3_5_unreadable_settings_read_as_off` |
| low | One invalid key silently resets every setting; legacy `config` subtree ignored | Documented in `load_settings` and design; a fixed warning is logged |
| info | The story is NEEDS CLARIFICATION; the setting ships before its scope is decided | Delivered as display-only and granting nothing (`test_us_3_5_setting_grants_nothing_yet`); SPECS.md keeps the open questions for the Product Manager |

## Re-verification

`make check` → exit 0. `pytest -m hermes -k us_3_5` → 3 passed (real Hermes config read).

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
