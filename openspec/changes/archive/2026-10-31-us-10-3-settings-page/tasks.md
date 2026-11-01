# Tasks

## 1. Gateway

- [x] 1.1 `GET /settings` answers `retention_days`; `POST /settings/retention` through `save_plugin_settings`; error codes; verify `test_us_10_3_retention_saved`, `test_us_10_3_retention_refusals`
- [x] 1.2 Gateway `GET /corpus/status` filtered to the active profile; route pins; verify `test_us_10_3_corpus_status_*`, `test_us_7_3_no_transmitting_route`

## 2. Page

- [x] 2.1 `SettingsPage` sections (worker, models, corpus, retention with Save); verify node `test_us_10_3_settings_registers_when_supported`, `test_us_10_3_settings_degrade_when_unsupported`, `test_us_10_3_pane_retention_saved`

## 3. Evidence

- [x] 3.1 Gateway-Python probe of the real Hermes writer; verify `test_us_10_3_retention_saved_with_hermes` (marker `hermes`)
- [x] 3.2 Record `evidence/US-10.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
