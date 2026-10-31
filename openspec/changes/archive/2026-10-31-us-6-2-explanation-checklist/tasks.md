# Tasks

## 1. Rule cards

- [x] 1.1 `RuleCard.required_documents` (only on `required_docs`), stored as JSON metadata; verify `test_us_6_2_required_documents_round_trip`, `test_us_6_2_list_on_another_topic_refused`
- [x] 1.2 `rule_card_of`, `payer_rule_cards` with whole-word, longest-match payer matching; verify `test_us_6_2_payer_cards_match_by_whole_words`

## 2. Explanation

- [x] 2.1 `cases/diagnosis.py` `Explanation`, `ChecklistItem`, `RuleCardRef` on `Diagnosis`; verify `test_us_6_2_explanation_and_root_cause_shown`
- [x] 2.2 `pipeline/explain.py` template, parser, checklist from item numbers; verify `test_us_6_2_checklist_lists_missing_docs`, `test_us_6_2_items_off_the_card_dropped`, `test_us_6_2_explanation_real_model` (marked `models`)
- [x] 2.3 `Diagnoser` `explaining` stage with two saves; verify `test_us_6_2_missing_explanation_model_keeps_classification`, `test_us_6_2_progress_relayed`

## 3. Pane and operations

- [x] 3.1 Pane explanation, root cause, checklist, rule card provenance; verify `node --test` `test_us_6_2_*`
- [x] 3.2 Runbook `case-diagnosis` rule-card section; verify `test_us_1_5_runbooks_have_sections`
- [x] 3.3 Record `evidence/US-6.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
