# Tasks

## 1. Types and routing

- [x] 1.1 `corrections/types.py` `CorrectableField`, `ClaimCorrection`, `CorrectedClaimDraft`, `RemedyAdvice`; `cases/diagnosis.py` `Remedy`; verify `test_us_7_4_label_is_always_present`, `test_us_7_4_value_missing_from_documents_is_never_invented`
- [x] 1.2 `corrections/remedy.py` `recommended_remedy` and `frequency_code`; verify `test_us_7_4_appeal_only_denial_gets_a_recommendation`, `test_us_7_4_codes_split_eligibility_and_missing_information`, `test_us_7_4_rule_card_overrides_the_table`, `test_us_7_4_unprocessable_claim_is_new`
- [x] 1.3 `corrected_claims` rule-card topic, six rule cards per case; verify `test_us_7_4_corrected_claims_card_imports`

## 2. Drafting

- [x] 2.1 `corrections/draft.py` planned changes, `correction_draft` template, reply parser; verify `test_us_7_4_value_missing_from_documents_is_never_invented`, `test_us_7_4_reply_that_proposes_a_code_is_refused`
- [x] 2.2 `Corrector` job kind `correct`, the `correction` case item, `Case.remedy`, `correction_stale`; verify `test_us_7_4_correctable_denial_gets_a_list_of_changes`, `test_us_7_4_draft_goes_stale_after_re_extraction`, `test_us_7_4_drafting_needs_a_current_diagnosis`
- [x] 2.3 Worker and gateway routes, `WorkerClient` methods, error codes; verify `test_us_7_4_correction_through_the_gateway_refusals`, `test_us_7_3_case_routes_reach_only_loopback`

## 3. Export, pane, operations

- [x] 3.1 Export as `corrected-claim-draft-*.{pdf,docx}`; verify `test_us_7_4_export_pdf_and_docx`
- [x] 3.2 Pane recommendation, Draft corrected claim, the labeled list, its exports; verify `node --test` `test_us_7_4_*`
- [x] 3.3 US-7.3 pins and walks cover the new routes and controls; verify `test_us_7_3_no_transmitting_route`, `test_us_7_3_case_routes_reach_only_loopback`, `test_us_7_4_no_submit_control`
- [x] 3.4 `make case-correct`, `make case-correction-export`, runbooks; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 3.5 Record `evidence/US-7.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
