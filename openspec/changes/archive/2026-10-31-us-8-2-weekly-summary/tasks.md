# Tasks

## 1. Opt-in and snapshot

- [x] 1.1 `share_outcome_stats` setting and manifest entry, `load_outcome_sharing` failing closed; verify `test_us_8_2_sharing_needs_an_explicit_true`, `test_us_8_2_sharing_fails_closed`, `test_us_1_1_config_schema_matches_settings`
- [x] 1.2 `OutcomeFeatures`, `outcome_features`, the `features` column and its migration; verify `test_us_8_2_outcome_takes_the_snapshot`, `test_us_8_2_a_correction_after_the_purge_keeps_the_snapshot`, `test_us_8_2_an_older_outcomes_table_gains_features`

## 2. Aggregation

- [x] 2.1 `read_outcomes` (read-only, no key, outcomes-only authorizer); verify `test_us_8_2_aggregation_reads_only_outcomes`, `test_us_8_2_an_oversized_stored_snapshot_is_unclassified`, `test_us_8_2_a_foreign_row_fails_only_its_profile`, `test_us_8_2_a_huge_claim_keeps_a_summary_snapshot`, `test_us_8_2_reader_can_open_nothing_else`, `test_us_8_2_reader_needs_no_key`
- [x] 2.2 `IsoWeek`, week bounds, `WeeklySummary`, `build_weekly_summary`; verify `test_us_8_2_only_opted_in_profiles`, `test_us_8_2_revoking_excludes_the_profile`, `test_us_8_2_counts_and_overturn_rate`, `test_us_8_2_week_bounds_in_the_local_zone`, `test_us_8_2_invalid_weeks`

## 3. Routes, dashboard, operations

- [x] 3.1 Worker and gateway `GET /outcomes/summary`, `WorkerClient.weekly_summary`, route pins; verify `test_us_8_2_summary_through_the_gateway`, `test_us_8_2_bad_weeks_through_the_gateway`, `test_us_7_3_no_transmitting_route`
- [x] 3.2 Dashboard route shows the summary per payer and denial reason and per payer and code; verify `node --test` `test_us_8_2_*`
- [x] 3.3 `make outcomes-summary`, runbook section; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.4 Record `evidence/US-8.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
