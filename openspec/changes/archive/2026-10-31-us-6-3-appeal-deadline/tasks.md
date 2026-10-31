# Tasks

## 1. Inputs

- [x] 1.1 `CaseExtraction.denial_date` (835 transaction header `DTM*405`/`GS04`/`BPR16`, the extraction template, confirmable, `YYYY-MM-DD` only); verify `test_us_6_3_835_gives_the_denial_date`, `test_us_6_3_835_dates_come_from_the_first_claims_transaction`, `test_us_6_3_older_extraction_loads`, `test_us_6_3_denial_date_confirmable`
- [x] 1.2 `RuleCard.appeal_limit_days` (strict, only on `appeal_levels`), round trip; verify `test_us_6_3_appeal_limit_round_trip`, `test_us_6_3_limit_on_another_topic_refused`

## 2. Deadline

- [x] 2.1 Pure `compute_deadline()` in `pipeline/deadline.py` (docstring cites US-6.3) and `appeal_deadline()`; verify `test_us_6_3_compute_deadline_is_pure`, `test_us_6_3_unknown_deadline_says_why`, `test_us_6_3_implausible_denial_date_is_not_used`
- [x] 2.2 `Case.deadline` computed by `CaseService` on every read; verify `test_us_6_3_deadline_from_rule_card`, `test_us_6_3_deadline_follows_the_case_without_a_model`, `test_us_6_3_no_rule_card`, `test_us_6_3_unreadable_denial_date`

## 3. Pane and operations

- [x] 3.1 Pane deadline line, passed flag, unknown reasons, Denial date field; verify `node --test` `test_us_6_3_*`
- [x] 3.2 Runbooks: `appeal_levels` card format, deadline checks, rollback limit; verify `test_us_1_5_runbooks_have_sections`
- [x] 3.3 Record `evidence/US-6.3/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
