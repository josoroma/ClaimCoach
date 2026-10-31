# Tasks

## 1. Draft model and storage

- [x] 1.1 `letters/types.py` `DraftRequest`, `AppealDraft`, `DRAFT_LABEL`; verify `test_us_7_1_draft_model_is_strict`
- [x] 1.2 `draft` case item, `case_drafted` audit, `Case.draft` and `draft_stale`; verify `test_us_7_1_draft_stale_after_confirmed_field`, `test_us_7_1_draft_purged_with_case`

## 2. Drafting

- [x] 2.1 `letters/draft.py` template, prompt data, reply parser, template choice; verify `test_us_7_1_template_chosen_by_denial_reason`, `test_us_7_1_prompt_carries_letter_facts`
- [x] 2.2 `Drafter` job kind `draft` with `drafting` progress; verify `test_us_7_1_draft_from_rule_card_and_template`, `test_us_7_1_unusable_reply_stores_nothing`
- [x] 2.3 Refusals before a job starts; verify `test_us_7_1_drafting_needs_a_current_diagnosis`, `test_us_7_1_no_letter_template`

## 3. Pane and operations

- [x] 3.1 Pane Draft appeal button, drafting progress, the labeled draft; verify `node --test` `test_us_7_1_*`, `test_us_7_1_draft_carries_review_label`
- [x] 3.2 `make case-draft` and the `appeal-drafting` runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.3 Record `evidence/US-7.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
