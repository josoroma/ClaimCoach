# Tasks

## 1. Pane

- [x] 1.1 Add the typed case API client and upload/open/process flow to `plugin/desktop/plugin.js`; verify `test_us_3_3_pane_uses_only_plugin_rest` (node --test) and `tsc --noEmit --checkJs`
- [x] 1.2 Source scan for agent surfaces; verify `test_us_3_3_plugin_js_never_references_agent_surfaces`
- [x] 1.3 Session check; verify `test_us_3_3_case_processing_adds_nothing_to_sessions` (node) and `test_us_3_3_case_processing_adds_nothing_to_sessions_backend` (pytest)
- [x] 1.4 Failure states; verify the "case API and pane states" node tests at 100% coverage (`make test-js`)

## 2. Evidence

- [x] 2.1 Record `evidence/US-3.3/test-report.md`, `junit.xml`, and `junit-node.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
