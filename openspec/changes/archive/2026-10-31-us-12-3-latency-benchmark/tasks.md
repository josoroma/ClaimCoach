# Tasks

## 1. Benchmark

- [x] 1.1 `evals/latency.py` (`benchmark_cases`, `median_seconds`, `run_latency`), `LatencyReport`, `CaseTiming`, `StageSeconds`; verify `test_us_12_3_latency_reports_median`, `test_us_12_3_median_over_target_blocks`, `test_us_12_3_failed_cases_count_as_slowest`, `test_us_12_3_a_failed_case_fails_the_gate`, `test_us_12_3_benchmark_mixes_document_kinds`
- [x] 1.2 Flow driver failures and the EOB PDF renderer; verify `test_us_12_3_flow_*`, `test_us_12_3_job_that_never_ends_times_out`, `test_us_12_3_a_finished_job_that_did_not_succeed_fails`, `test_us_12_3_refused_step_is_its_error_code`, `test_us_12_3_no_case_means_nothing_to_purge`, `test_us_12_3_purge_failure_is_reported`, `test_us_12_3_eob_pdf_is_rendered_from_text`

## 2. Operations and evidence

- [x] 2.1 `python -m claimcoach.evals latency`, `make eval-latency`; runbook section; verify story-tester operator run, `test_us_12_3_latency_on_this_mac` (models)
- [x] 2.2 Record `evidence/US-12.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
