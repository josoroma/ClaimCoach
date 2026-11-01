# Tasks

## 1. Eval scaffolding

- [x] 1.1 `evals/types.py` (`EvalResult`, `Score`, targets, exit codes) and `evals/report.py` (atomic JSON under `evidence/US-12.x/`, terminal summary); verify `test_us_12_1_gate_passes_at_target`, `test_us_12_1_report_is_replaced_whole`
- [x] 1.2 `evals/datasets.py` `load_phi_set` (strict, size-capped, file named but never echoed); verify `test_us_12_1_unreadable_set_is_not_measured`, `test_us_12_1_oversized_set_is_refused`

## 2. Redaction recall

- [x] 2.1 `evals/redaction_recall.py` (`redact_set`, `score_redaction`, `leaks`, `run_redaction`); verify `test_us_12_1_gate_passes_at_target`, `test_us_12_1_gate_blocks_below_target`, `test_us_12_1_recall_exactly_at_target_passes`, `test_us_12_1_unredactable_documents_miss_every_value`, `test_us_12_1_leaks_whole_words_only`, `test_us_12_1_report_names_no_phi_value`
- [x] 2.2 `python -m claimcoach.evals redaction`; verify `test_us_12_1_no_worker_is_not_measured`, `test_us_12_1_port_outside_the_range_is_refused`, `test_us_12_1_gate_on_real_models` (models)

## 3. Operations and evidence

- [x] 3.1 `make eval-redaction`, `make evals`, `make release-gate`; `evals-release-gates` runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.2 Record `evidence/US-12.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
