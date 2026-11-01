# Review: US-9.2

Change: us-9-2-case-summary-tool
Reviewer: independent `story-reviewer` agent (read-only, given the change names and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the four EPIC-9 changes
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The handler read `active_profile()` inside the coroutine that `run_blocking` runs on a new thread, which starts with an empty context. Hermes v0.22.5 names a Desktop session's profile in the context variable `_HERMES_HOME_OVERRIDE`, so the worker was asked for the launch profile: a session of profile `alice` could get another profile's case summarized and audited in the wrong log (BR-5). The reviewer reproduced it with a context-variable stand-in for `hermes_constants` | `run_blocking` runs the call in `contextvars.copy_context()` of the caller, so context variables carry over (this covers the guard's redaction calls too). `test_us_9_2_the_sessions_profile_reaches_the_worker` injects a `hermes_constants` whose `get_hermes_home` reads a ContextVar, sets the override to `alice`, and asserts alice's case is summarized and audited as `alice` while the launch profile's case is `case_not_found` with no audit entry. The test fails with the copy removed and passes with it |
| low | A profile with no user scope answered `profile_not_found`, while the spec says another profile's case is `case_not_found` | `case_summary` answers `case_not_found` for a profile without cases. `test_us_9_2_other_profiles_case_not_found` and the US-9.4 tests updated |
| medium | SPECS.md marked EPIC-9 done before any `evidence/US-9.x` existed | Evidence recorded by independent `story-tester` runs after the fixes, before the changes are archived and anything is committed |

Also checked by the reviewer and found sound: the summary is de-identified by construction (rule-card payer only, `CaseCode` codes, enums, counts, no dates); stage and status logic; one parameter (`case_id`) with `extra="forbid"`; the `case_summarized` audit; the route's `ProfileName` validation.

## Re-verification

See the EPIC-9 `make verify` result recorded in `us-9-4-denial-command/review.md`.
