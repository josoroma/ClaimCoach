# Tasks

## 1. Command

- [x] 1.1 `/denial` guide and case summary text over the guarded handler; verify `test_us_9_4_denial_returns_text_without_phi`, `test_us_9_4_denial_summarizes_a_case`, `test_us_9_4_arguments_are_never_echoed`, `test_us_9_4_failures_are_fixed_messages`
- [x] 1.2 Register with `ctx.register_command`; verify `test_us_9_4_command_registered`, `test_us_9_4_real_hermes_command` (hermes)
- [x] 1.3 `make agent-denial`; verify story-tester operator run
- [x] 1.4 Record `evidence/US-9.4/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
