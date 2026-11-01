# Review: US-14.2

Change: us-14-2-remove-models-home-setting
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Task 2.1 ticked before evidence existed | `evidence/US-14.2/` recorded before archiving |
| low | The MODELS_HOME check used the helper, not the worker's wiring | `test_us_14_2_setting_removed` runs `worker.__main__.main` and reads its `ModelManager.models_home` |
| low | `RETIRED_SETTINGS == {...}` tested a constant | Now asserts `models_home` is retired and no live field is in `RETIRED_SETTINGS` |
| low | `load_settings`' docstring still said any unknown key resets every setting | It says retired keys are dropped first |

## Re-verification

```text
$ make verify
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
