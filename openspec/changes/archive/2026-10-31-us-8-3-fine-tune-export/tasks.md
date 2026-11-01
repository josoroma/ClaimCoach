# Tasks

## 1. Records

- [x] 1.1 `ClaimFacts` (payment statuses, no amounts) and the appeal likelihood in the snapshot; `FineTuneRecord`; verify `test_us_8_3_amounts_are_reduced_to_a_payment_status`, `test_us_8_3_a_record_is_what_the_classifier_read`, `test_us_8_3_only_labeled_outcomes_of_sharing_profiles`
- [x] 1.2 The regex guard; verify `test_us_8_3_exported_pairs_contain_no_phi`, `test_us_8_3_a_record_a_validator_matches_is_withheld`

## 2. Approval and files

- [x] 2.1 `ExportApproval`, `export_not_approved` before any read; verify `test_us_8_3_export_requires_approval`, `test_us_8_3_approval_is_strict`
- [x] 2.2 Owner-only file, approval log, no partial file on failure, no symlink, no unlogged export; verify `test_us_8_3_files_are_owner_only_and_approvals_logged`, `test_us_8_3_a_failed_write_leaves_nothing`, `test_us_8_3_an_export_is_never_left_unlogged`, `test_us_8_3_the_approval_log_is_never_followed_through_a_link`, `test_us_8_3_the_approval_log_must_be_a_regular_file`, `test_us_8_3_the_fine_tune_folder_is_never_a_link`

## 3. Routes, dashboard, operations

- [x] 3.1 Worker and gateway `POST /outcomes/export`, `WorkerClient.export_fine_tune`, route pins; verify `test_us_8_3_export_through_the_gateway`, `test_us_8_3_refusals_through_the_gateway`, `test_us_7_3_no_transmitting_route`
- [x] 3.2 Dashboard Fine-tune export section; verify `node --test` `test_us_8_3_*`
- [x] 3.3 `make outcomes-export`, runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.4 Record `evidence/US-8.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
