# Tasks

## 1. Answers

- [x] 1.1 `ExplainCodeResult`, `PayerRulesResult`, `code_keys`, `explain_code`, `payer_rules`; verify `test_us_9_1_explain_code_from_global`, `test_us_9_1_payer_rules_returns_card`, `test_us_9_1_code_shapes`, `test_us_9_1_unknown_code_is_not_found`, `test_us_9_1_unknown_payer_is_not_found`, `test_us_9_1_zero_padded_codes_are_one_code`, `test_us_9_1_long_reference_text_is_cut`
- [x] 1.2 Worker routes, client calls, `code_not_found`/`payer_not_found`, route pins; verify `test_us_9_1_tools_through_the_worker`, `test_us_7_3_no_transmitting_route`

## 2. Handlers

- [x] 2.1 `ToolSpec` with result model and worker call, behind the guard; verify `test_us_9_1_schemas_from_params`, `test_us_9_1_handler_failures_are_envelopes`, `test_us_1_1_tools_answer_an_envelope_without_a_worker`, `test_us_3_2_*`
- [x] 2.2 `make agent-tools`, `make agent-call`, `agent-tools` runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 2.3 Record `evidence/US-9.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
