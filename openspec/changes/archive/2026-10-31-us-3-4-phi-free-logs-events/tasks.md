# Tasks

## 1. Logs

- [x] 1.1 Add `claimcoach/logs.py` (`JsonFormatter`, `PhiRedactionFilter`, `get_logger`, `configure_logging`, `job_context`) and `claimcoach/redact/ledger.py`; split `claimcoach/redact/spans.py`; verify `test_us_3_4_foreign_loggers_are_scrubbed_by_the_formatter`, `test_us_3_4_exception_text_is_never_logged`, `test_us_3_4_ledger_is_bounded_and_skips_short_values`, `test_us_3_4_request_and_job_ids`
- [x] 1.2 Worker request IDs, sweep/acquire job IDs, JSON logging in `python -m claimcoach.worker`; every module uses `get_logger`; verify `test_us_3_4_logs_json_without_document_text`, `test_us_2_2_worker_main_rejects_invalid_registry`

## 2. Events

- [x] 2.1 Add `claimcoach/events.py` (`CaseProgressEvent`, `publish`, `hermes_sink`); verify `test_us_3_4_events_carry_no_phi`, `test_us_3_4_event_payloads_reject_free_text`, `test_us_3_4_event_fields_cannot_carry_text`, `test_us_3_4_publish_uses_hermes_broadcast_inside_the_gateway`

## 3. Evidence

- [x] 3.1 Record `evidence/US-3.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
