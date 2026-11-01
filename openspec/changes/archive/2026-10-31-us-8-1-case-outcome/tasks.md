# Tasks

## 1. Store and service

- [x] 1.1 `CorpusStore.record_outcome` closes the case in the same transaction, keeps the first close date, audits `case_closed` only on the close; verify `test_us_8_1_outcome_recorded`, `test_us_8_1_a_later_outcome_corrects_the_first`
- [x] 1.2 `OutcomeRequest`, `Case.outcome`, `CaseService.record_outcome`; verify `test_us_8_1_case_shows_its_outcome`

## 2. Routes

- [x] 2.1 Worker `POST /cases/{case_id}/outcome` (`model_busy` while a job runs), gateway route, `WorkerClient.record_outcome`, route pins; verify `test_us_8_1_outcome_through_the_worker`, `test_us_8_1_outcome_recorded` (through the gateway), `test_us_8_1_outcome_refused_while_a_job_runs`, `test_us_8_1_outcome_waits_for_a_real_job`, `test_us_8_1_invalid_outcomes`, `test_us_7_3_no_transmitting_route`

## 3. Pane and operations

- [x] 3.1 Pane Outcome section with the three Mark buttons, a confirmation before an open case closes, and a closed case's editing controls disabled; verify `node --test` `test_us_8_1_*`
- [x] 3.2 `make case-outcome`, `outcomes-and-export` runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.3 Record `evidence/US-8.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
