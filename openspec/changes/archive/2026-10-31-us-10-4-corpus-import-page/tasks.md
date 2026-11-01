# Tasks

## 1. Backend

- [x] 1.1 `parse_bundle_bytes`, location sanitizing, `BundlePreview`; verify `test_us_10_4_invalid_bundle_refused`, `test_us_4_3_*`
- [x] 1.2 Gateway preview and import routes, `invalid_bundle` and `import_not_confirmed`, the import timeout, route pins; verify `test_us_10_4_bundle_previewed`, `test_us_10_4_import_after_confirmation`, `test_us_10_4_unconfirmed_import`, `test_us_7_3_no_transmitting_route`

## 2. Page

- [x] 2.1 Settings page Global corpus import section; verify node `test_us_10_4_pane_*`

## 3. Evidence

- [x] 3.1 Runbook steps; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.2 Record `evidence/US-10.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
