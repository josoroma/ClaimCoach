# Test Report: US-3.5 Richer Agent Access When the Hermes Model Is Local

Change: us-3-5-richer-agent-access-setting
Story: US-3.5
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), run after implementation and independent review
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Richer access is off by default: Then the richer agent access setting is off" | PASS | `test_us_3_5_richer_access_off_by_default`: `plugin.yaml` default `false`, `ClaimCoachSettings()` false, `load_settings()` false outside Hermes and with a fresh Hermes config, gateway `GET /settings` → `richer_agent_access: false`. `test_us_3_5_real_hermes_config_is_read[None]` (real Hermes `load_config_readonly`, fresh config) → `False`. `test_us_3_5_unreadable_settings_read_as_off` (5 cases). Statusbar: `test_us_3_5_richer_access_off_by_default_in_statusbar` → `Local-only` |
| 2 | "Statusbar reflects richer access: Then the ClaimCoach item shows that richer agent access is enabled" | PASS | `test_us_3_5_statusbar_reflects_richer_access` (node --test): the registered `statusbar.right` item reads `/settings` and re-renders as `Local-only · richer agent access on`, tooltip says results are still redacted. `test_us_3_5_settings_route_reports_the_stored_value` and `test_us_3_5_real_hermes_config_is_read[True]` (real Hermes config) → true |

## Evidence Commands

```bash
make evidence STORY=US-3.5
```

```text
====================== 14 passed, 700 deselected in 0.94s ======================
  ✔ test_us_3_5_statusbar_reflects_richer_access
  ✔ test_us_3_5_richer_access_off_by_default_in_statusbar
```

Artifacts: `evidence/US-3.5/junit.xml`, `evidence/US-3.5/junit-node.xml`

## Failures

None.

## Notes

- SPECS.md keeps US-3.5 NEEDS CLARIFICATION: what richer access allows and how a local Hermes
  model is detected are open. This change delivers only the two scenarios; the setting grants
  nothing (`test_us_3_5_setting_grants_nothing_yet`), and agent tool results stay redacted.
- No live Desktop statusbar was rendered; the node test drives the registered contribution.
- After independent review: `richer_agent_access` is a `StrictBool` (`"yes"`, `1`, `"true"` read as
  off), invalid stored settings log a fixed warning, and the statusbar re-reads `/settings` every
  15 s (`test_us_3_5_statusbar_follows_a_changed_setting`).
