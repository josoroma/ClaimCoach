# Tasks

## 1. Fix

- [x] 1.1 `--port` on the worker-backed corpus subcommands, range-checked; verify `test_us_4_3_corpus_cli_reaches_a_worker_on_another_port`, `test_us_4_3_corpus_cli_sends_the_token_only_to_the_recorded_worker`, `test_us_4_3_corpus_cli_port_defaults_and_scope`, `test_us_4_3_corpus_cli_refuses_a_port_outside_the_range`, `test_us_4_3_hermes_claimcoach_corpus_import_help`
- [x] 1.2 Makefile `CORPUS_PORT` on the six worker-backed targets; verify `test_us_4_3_corpus_targets_pass_worker_port`
- [x] 1.3 Corpus runbook names `WORKER_PORT`; verify `test_us_4_3_corpus_runbook_names_the_worker_port`, `test_us_1_5_runbooks_have_sections`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
