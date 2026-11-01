# Tasks

## 1. Summary

- [x] 1.1 `CaseSummaryParams` (case ID only) and `CaseSummaryResult`; verify `test_us_9_2_summary_accepts_only_case_id`
- [x] 1.2 `case_summary` in the worker: stages, rule-card payer, current codes, deadline status, counts, `case_summarized` audit; verify `test_us_9_2_summary_redacted`, `test_us_9_2_summary_stages`, `test_us_9_2_printed_payer_never_returned`, `test_us_9_2_summary_is_audited`
- [x] 1.3 Worker route, client call, active profile; verify `test_us_9_2_other_profiles_case_not_found`, `test_us_9_2_the_sessions_profile_reaches_the_worker`, `test_us_7_3_no_transmitting_route`
- [x] 1.4 Record `evidence/US-9.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
