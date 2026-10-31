# Tasks

## 1. Detector and validators

- [x] 1.1 Add `claimcoach/redact/types.py` (`PhiCategory`, `PhiSpan`, `RedactionResult`, `RedactRequest`, `RedactResponse`); verify `test_us_3_1_types_validate`
- [x] 1.2 Add `claimcoach/redact/validators.py`; verify `test_us_3_1_validator_matches`, `test_us_3_1_validators_ignore_codes_and_unlabeled_dates`, `test_us_3_1_regex_validators_cover_structured_categories`
- [x] 1.3 Add `claimcoach/models/chat.py` and `claimcoach/redact/detector.py` (Qwen3-8B JSON span prompt via the prompt builder); verify `test_us_3_1_detector_prompt_keeps_document_in_data_section`, `test_us_3_1_parse_reply`, `test_us_3_1_unusable_reply_fails_closed`, `test_us_3_1_truncated_reply_fails_closed`, `test_us_3_1_model_errors_are_model_unavailable`
- [x] 1.4 Add `claimcoach/redact/redactor.py` (`redact()`, `Redactor`); verify `test_us_3_1_spans_carry_category_with_fake_model`, `test_us_3_1_redacted_text_replaces_spans`, `test_us_3_1_second_pass_catches_what_spans_missed`, `test_us_3_1_propagation_redacts_every_form_of_a_name`
- [x] 1.5 Real-model test; verify `test_us_3_1_spans_carry_category` (`make test-models`)

## 2. Fixtures

- [x] 2.1 Generate `tests/fixtures/phi/phi_set.json` (synthetic, seeded); verify `test_us_3_1_fixtures_are_reproducible`

## 3. Worker and operations

- [x] 3.1 Worker `POST /redact` and `redaction_failed`; verify `test_us_3_1_worker_redact_route`, `test_us_3_1_worker_redact_failure_is_an_envelope`
- [x] 3.2 Makefile `redact`, `phi-fixtures`, `test-story`, `test-models`, `doctor`, `start`, `stop`, `gateway-restart`, `plugin-install`; runbook `phi-redaction.md`; verify `test_us_1_5_runbooks_have_sections` and a live `make doctor`
- [x] 3.3 Record `evidence/US-3.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
