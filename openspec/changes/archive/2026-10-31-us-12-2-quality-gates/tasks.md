# Tasks

## 1. Labeled set and case flow

- [x] 1.1 `tests/fixtures/denials/generate.py` and `denial_set.json`; `DenialEvalSet`, `DraftReviewSet`; verify `test_us_12_2_denial_set_is_reproducible`, `test_us_12_2_each_label_is_signaled_by_its_code`, `test_us_12_2_review_file_is_strict`
- [x] 1.2 `evals/flow.py` `run_case` and `WorkerDriver` (attach by kind, wait on job events, purge afterwards); verify `test_us_12_2_every_eval_case_is_purged`, `test_us_12_2_unpurgeable_cases_are_reported`

## 2. Evals

- [x] 2.1 `evals/classification.py`; verify `test_us_12_2_classification_eval_reports_accuracy`, `test_us_12_2_classification_passes_at_target`, `test_us_12_2_cases_without_a_diagnosis_are_misses`, `test_us_12_2_limit_runs_the_first_cases`, `test_us_12_2_classification_on_real_models` (models)
- [x] 2.2 `evals/draft_acceptance.py` (rubric, per-reason rate); verify `test_us_12_2_similarity_of_letters`, `test_us_12_2_draft_acceptance_gate`, `test_us_12_2_draft_reviews_group_by_reason`

## 3. Operations and evidence

- [x] 3.1 `python -m claimcoach.evals classification|drafts`, `make eval-classification`, `make eval-drafts`; runbook; verify `test_us_12_2_limit_must_be_positive`, story-tester operator run
- [x] 3.2 Record `evidence/US-12.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
