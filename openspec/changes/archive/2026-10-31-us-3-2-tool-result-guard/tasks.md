# Tasks

## 1. Guard

- [x] 1.1 Add `claimcoach/agent/guard.py` (`redact_tool_result`, `guard_text`, `make_hook`, `register_guard_hook`, `worker_scrubber`); `WorkerClient.redact`; verify `test_us_3_2_tool_results_phi_free_without_hook`, `test_us_3_2_json_results_are_redacted_field_by_field`
- [x] 1.2 Register wrapped handlers and the hook (`register_agent`, `plugin/__init__.py`); verify `test_us_3_2_every_registered_handler_is_guarded`, `test_us_1_1_agent_half_registers_provided_tools`
- [x] 1.3 Hook; verify `test_us_3_2_hook_re_redacts`, `test_us_3_2_hook_leaves_other_tools_alone`
- [x] 1.4 Fail closed; verify `test_us_3_2_failing_hook_does_not_expose_phi`, `test_us_3_2_unreachable_worker_fails_closed`, `test_us_3_2_slow_redaction_times_out_closed`, `test_us_3_2_handler_exception_text_never_reaches_the_agent`, `test_us_3_2_redaction_that_loses_a_field_is_withheld`
- [x] 1.5 Real Hermes dispatch; verify `test_us_3_2_real_hermes_dispatch_is_guarded` (`pytest -m hermes`)

## 2. Evidence

- [x] 2.1 Record `evidence/US-3.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make check` and the tests named there
