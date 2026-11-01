# Tasks

## 1. Settings

- [x] 1.1 Remove `models_home` from `ClaimCoachSettings` and `plugin.yaml`; drop a stored one in `load_settings`; verify `test_us_14_2_setting_removed`, `test_us_14_2_saved_models_home_ignored`, `test_us_14_2_other_unknown_settings_still_reset`, `test_us_1_1_config_schema_matches_settings`
- [x] 1.2 Update README-DEV.md Configuration and the upgrade runbook; verify `test_us_13_2_settings_documented`

## 2. Evidence

- [x] 2.1 Record `evidence/US-14.2/test-report.md` and `junit.xml`; verify `make evidence-check`
