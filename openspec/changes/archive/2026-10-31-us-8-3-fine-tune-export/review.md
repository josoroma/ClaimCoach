# Review: US-8.3

Change: us-8-3-fine-tune-export
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the EPIC-8 changes
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | The export was renamed into place before the approval was logged: a log that could not be written (a link, a folder, a full disk) left an export nobody approved on record | The log is opened, and checked, before the export is written; if its line cannot be written the export is deleted. `test_us_8_3_an_export_is_never_left_unlogged`; the link test now also asserts no export is left |
| low | The tests could not catch that: the link test checked only the link's target, and the failed-write test failed only the export | `failing_fdopen` fails either write; both tests assert the folder holds no export |
| low | `ManagerName` accepted U+0085, U+2028, and U+2029, which split one log entry into several lines for common readers | A name must be `str.isprintable()`; `test_us_8_3_approval_is_strict` covers all three |
| low | An existing log was reused whatever its mode or type; a FIFO there blocked a worker thread | Opened `O_NONBLOCK`, refused unless a regular file of this user, made 0600; `test_us_8_3_the_approval_log_must_be_a_regular_file` (with and without a FIFO reader), `test_us_8_3_an_existing_log_is_made_owner_only` |
| low | `make outcomes-export MANAGER='Dana $Lee'` recorded `Dana ee`: make expands exported command-line values | `override MANAGER := $(value MANAGER)`; checked by hand with a probe target: `'Dana $Lee'` and `'Dana $(shell echo x)'` reach the worker as typed |
| low | A `CONFIRM=yes` exported in the shell approved `make outcomes-export` without being typed | The target sends `approved: true` only when `CONFIRM` comes from the command line (`$(origin CONFIRM)`); checked by hand with `env CONFIRM=yes make -n …` |
| low | (shared) `_secure` followed a symbolic link in a ClaimCoach folder's place, so exports would land wherever it pointed (also the US-7.2 exports folder) | `_secure` refuses a link; `test_us_8_3_the_fine_tune_folder_is_never_a_link` |
| low | The export window ended at "now", so an outcome stamped after a clock was set back was silently dropped | The window has no upper bound; `test_us_8_3_outcomes_recorded_after_a_clock_change_are_exported` |
| info | A ZIP code mis-read as a CPT code and confirmed cannot be told apart by the guard | Recorded under Risks / Trade-offs. Separately, the US-8.2 review led to dropping every dollar amount from the facts (payment status only; design decision 1) |

Also checked by the reviewer and found sound: the refusal before any read (`fine_tune_dir` never touched; 403 from worker and gateway; 422 for a non-JSON body or a non-boolean `approved`); every record field is an enum, a pattern-checked code, or a rule-card payer name, and facts are kept only for a diagnosis of the current fields; the PHI test's seeded payer name and member ID; logs carry counts only; strict, frozen models; `ERROR_MESSAGES` and `RELAYED_CODES`; `O_EXCL | O_NOFOLLOW` partial files with random names; concurrent appends; the shared reader; route pins; the dashboard's approval gating and untick after each export; the Makefile's JSON built from the environment; no network surface (BR-1, BR-11, BR-12).

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-8 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1304 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 117 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-8.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by independent `story-tester` agents after the fixes, each
with an operator run against its own scratch worker (synthetic data, fake models, loopback ports
18211–18213, never `~/.hermes`): `make case-outcome` (bad values, busy, record, correction,
audit), `make outcomes-summary` (opted-in versus not, revoked, bad weeks, one read-only connection
to the opted-in profile only), and `make outcomes-export` (refused without a name, without
`CONFIRM=yes`, and with `CONFIRM` only in the shell; approved: 0600 file, one log line, none of the
seeded PHI strings). `hermes plugins validate plugin/` passed on the updated manifest.
