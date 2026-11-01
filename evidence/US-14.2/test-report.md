# Test Report: US-14.2 Remove the Unread models_home Setting

Change: us-14-2-remove-models-home-setting
Story: US-14.2
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; no live Hermes Desktop; no real models

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The setting is removed: Then it has no models_home setting" | PASS | `test_us_14_2_setting_removed`: neither `plugin.yaml`'s `config_schema` nor `ClaimCoachSettings` has `models_home`, and the two still agree (`test_us_1_1_config_schema_matches_settings` too) |
| 2 | "The setting is removed: And the worker still takes the weights folder from MODELS_HOME" | PASS | Same test: `claimcoach.worker.__main__.main` with `uvicorn.run` stubbed builds its `ModelManager` with `models_home` equal to `$MODELS_HOME` |
| 3 | "A saved models_home does not reset the other settings: Then models_home is ignored and every other saved setting keeps its value" | PASS | `test_us_14_2_saved_models_home_ignored`: a stored `models_home` with five non-default values loads as those five values; `RETIRED_SETTINGS` holds no live setting. `test_us_14_2_other_unknown_settings_still_reset`: any other unknown key still resets to the defaults (US-3.5) |

## Evidence Commands

```bash
make evidence STORY=US-14.2
make verify
```

```text
====================== 3 passed, 1823 deselected in 1.40s ======================
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

Artifacts: `evidence/US-14.2/junit.xml`

## Failures

None.

## Notes

- The reviewer also ran every per-profile reader and real Hermes `load_config_readonly` / `save_plugin_settings` with a saved `models_home`; all kept the other values.
- Review fixes (see review.md): the worker-wiring check, a behavioural `RETIRED_SETTINGS` check, and the `load_settings` docstring.
