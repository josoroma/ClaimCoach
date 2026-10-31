# Tasks

## 1. Setting

- [x] 1.1 Add `richer_agent_access` to `ClaimCoachSettings` and `plugin.yaml`; `load_settings()`; verify `test_us_3_5_richer_access_off_by_default`, `test_us_3_5_unreadable_settings_read_as_off`, `test_us_1_1_config_schema_matches_settings`
- [x] 1.2 Gateway `GET /settings`; verify `test_us_3_5_settings_route_reports_the_stored_value`
- [x] 1.3 Real Hermes config; verify `test_us_3_5_real_hermes_config_is_read` (`pytest -m hermes`)
- [x] 1.4 The setting grants nothing; verify `test_us_3_5_setting_grants_nothing_yet`

## 2. Statusbar

- [x] 2.1 `LocalOnlyIndicator` reads `/settings`; verify `test_us_3_5_statusbar_reflects_richer_access`, `test_us_3_5_richer_access_off_by_default_in_statusbar` (node --test)

## 3. Evidence

- [x] 3.1 Record `evidence/US-3.5/test-report.md`, `junit.xml`, and `junit-node.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
