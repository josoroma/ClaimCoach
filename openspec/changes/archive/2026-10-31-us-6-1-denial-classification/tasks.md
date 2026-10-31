# Tasks

## 1. Diagnosis

- [x] 1.1 `cases/diagnosis.py` typed `DenialReason`, `AppealLikelihood`, `Diagnosis`; verify `test_us_6_1_classification_typed_result`, `test_us_6_1_diagnosis_model_is_strict`
- [x] 1.2 `corpus/lookup.py` code notes and `CorpusStore.documents(kind=...)`; verify `test_us_6_1_code_notes_are_exact`
- [x] 1.3 Case item kind `diagnosis` with the `case_items` CHECK migration; verify `test_us_6_1_case_items_check_migrates`, `test_us_6_1_diagnosis_purged_with_case`
- [x] 1.4 `pipeline/diagnose.py` template, facts, parser, `Diagnoser`; verify `test_us_6_1_classification_typed_result`, `test_us_6_1_reply_outside_closed_set_fails`, `test_us_6_1_prompt_carries_only_facts`, `test_us_6_1_classification_real_model` (marked `models`)
- [x] 1.5 `JobRegistry` job kinds, worker and gateway `/diagnose`; verify `test_us_6_1_diagnosis_requires_extraction`, `test_us_6_1_progress_relayed`, `test_us_6_1_one_job_per_case`

## 2. Case and pane

- [x] 2.1 `Case.diagnosis`, `diagnosis_stale`; verify `test_us_6_1_likelihood_includes_reasons`, `test_us_6_1_confirmed_field_makes_diagnosis_stale`
- [x] 2.2 Pane: diagnosis view, chained diagnosis, Diagnose button; verify `node --test` `test_us_6_1_*`

## 3. Operations

- [x] 3.1 Makefile `case-diagnose`; runbook `case-diagnosis`; verify `test_us_1_5_runbooks_have_sections`
- [x] 3.2 Record `evidence/US-6.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
