# Tasks

## 1. Audit

- [x] 1.1 `claimcoach/egress.py` (`is_loopback`, `EgressRecord`, `EgressAudit`, `file_sink`, `read_records`); the test socket guard reuses `is_loopback`; verify `test_us_12_4_audit_hook_is_added_once`, `test_us_12_4_audit_hook_keeps_only_non_loopback`, `test_us_12_4_record_file_is_owner_only`, `test_us_12_4_unreadable_records_still_count`, `test_us_1_4_*`
- [x] 1.2 The worker starts the audit before loading the registry; verify `test_us_12_4_worker_starts_the_audit`

## 2. Check

- [x] 2.1 `GatewayDriver` / `gateway_driver` in `evals/flow.py`; verify `test_us_12_4_gateway_refusals_are_error_codes`, `test_us_12_4_gateway_non_envelope_failure_is_worker_error`, `test_us_12_4_gateway_job_that_never_ends_times_out`
- [x] 2.2 `evals/egress_check.py` (preconditions, `app_processes`, `parse_lsof`, `sample_lsof`, `run_egress_check`); verify `test_us_12_4_full_flow_no_non_loopback_connection`, `test_us_12_4_plugin_api_attempt_is_caught`, `test_us_12_4_worker_records_during_the_flow_are_caught`, `test_us_12_4_lsof_connection_is_caught`, `test_us_12_4_a_stopped_flow_does_not_pass`, `test_us_12_4_sampler_failure_is_raised`, `test_us_12_4_parse_lsof`, `test_us_12_4_lsof_failure_is_an_error`, `test_us_12_4_preconditions`, `test_us_12_4_processes_are_the_worker_and_its_model_servers`
- [x] 2.3 US-7.3 pins name `evals/flow.py` and `evals/egress_check.py`; verify `test_us_7_3_http_clients_only_in_loopback_modules`

## 3. Operations and evidence

- [x] 3.1 `python -m claimcoach.evals egress`, `make eval-egress`; runbook section; verify `test_us_12_4_cli_*`, story-tester operator run, `test_us_12_4_full_flow_on_the_running_app` (models)
- [x] 3.2 Record `evidence/US-12.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
