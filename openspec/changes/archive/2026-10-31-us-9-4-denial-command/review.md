# Review: US-9.4

Change: us-9-4-denial-command
Reviewer: independent `story-reviewer` agent (read-only, given the change names and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the four EPIC-9 changes
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | (shared, see US-9.2) `/denial <case ID>` ran the summary on a thread without the caller's context, so a Desktop session's profile override was lost | Fixed in `run_blocking` (`contextvars.copy_context()`); `test_us_9_2_the_sessions_profile_reaches_the_worker` |
| low | `/denial <word>` answered `profile_not_found` for a profile with no cases | `case_not_found` now (US-9.2 fix); `test_us_9_4_unknown_case_is_a_fixed_message`, `test_us_9_4_cli_runs_denial` updated |

Also checked by the reviewer and found sound: the handler never raises and never echoes its argument; the reply is rendered only from a `CaseSummaryResult` that validates after redaction or from a known envelope's fixed message; every `DeadlineStatus` has a phrase; Hermes' `invoke_plugin_command` calls a one-argument handler with the raw text; sync handlers run on Hermes' executor.

## Re-verification

`make verify` → exit 0 on the fixed tree with all four EPIC-9 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1397 offline pytest tests passed at 100% line and
branch coverage of `plugin/` (6423 statements, 1086 branches); 117 node tests at 100% line,
branch, and function coverage of `plugin.js`; evidence-check `ok` for every report through US-9.4
(OhMyOrch accepted each); 2 gate self-tests passed. Evidence was recorded by two independent
`story-tester` agents after the fixes, each with an operator run against its own scratch worker
(synthetic data, fake models, loopback ports 18215 and 18216, never `~/.hermes`): `make
agent-tools`, `make agent-call` for all three tools (results, refusals, no echo, PHI scan of the
case summary, `case_summarized` audit), `make agent-skill`, `make agent-denial` (guide, summaries,
no echo, PHI scan of 14 replies), and `make agent-probe` (5 tests through Hermes Agent v0.22.5:
the tools, the skill, and `/denial` register; `skill_view("claimcoach:denial-triage")` serves the
playbook).
