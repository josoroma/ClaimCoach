# Tasks

## 1. Backend

- [x] 1.1 `CaseListEntry`, `CorpusStore.case_index`, `CaseService.list_cases`; verify `test_us_10_1_case_list_holds_no_content`, `test_us_10_1_list_*`
- [x] 1.2 Worker and gateway `GET /cases`, `WorkerClient.list_cases`, route pins; verify `test_us_10_1_list_through_the_gateway`, `test_us_7_3_no_transmitting_route`

## 2. Pane

- [x] 2.1 `ClaimCoachPane`, `CaseListView`, the link between list and detail; verify node `test_us_10_1_case_pane_registered`, `test_us_10_1_listed_case_opens`
- [x] 2.2 Dashboard route and sidebar entry; verify node `test_us_10_1_dashboard_route_registered`
- [x] 2.3 Error state; verify node `test_us_10_1_backend_errors_render_error_state`

## 3. Evidence

- [x] 3.1 `make case-list`; verify story-tester operator run
- [x] 3.2 Record `evidence/US-10.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
