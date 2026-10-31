# Review: US-4.5

Change: us-4-5-retention-purge
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-6-case-access-audit
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | An unreadable config or an invalid *unrelated* setting reset retention to 90 days, so a 365-day practice could lose cases irreversibly | `load_retention_days(home)` validates `retention_days` on its own and fails closed: unreadable or invalid → the profile is skipped (`PurgeResponse.skipped`) and retried next run; `test_us_4_5_untrusted_retention_skips_the_profile[0, thirty, None, 5000]`, `test_us_4_5_unrelated_invalid_setting_keeps_retention` |
| high | The scheduled purge ran sync Keychain/SQLite work on the event loop | `asyncio.to_thread`; store-opening routes in the thread pool; `test_us_4_5_purge_runs_off_the_event_loop` |
| medium | Backups kept purged PHI; runbook silent | phi-purge runbook step 3 (expire backups); design risk |
| low | `purge_all` caught only `CorpusError` | Also `sqlite3.Error` and `ValidationError`, per profile; `test_us_4_5_storage_error_in_one_profile_does_not_stop_others` |
| low | Timestamps with local offsets compared wrongly as text | Every stored timestamp is UTC; `test_us_4_5_close_times_compare_in_utc` |
| low | Checkpoint result ignored | `CorpusStore.checkpoint()` logs a blocked checkpoint and returns `False`; the next purge retries; `test_us_4_5_blocked_checkpoint_is_reported` |
| low | Re-closing restarted the retention clock | `COALESCE(closed_at, ?)`; `test_us_4_5_closing_again_keeps_the_retention_clock` |
| low | Lifespan teardown could skip shutdowns | See US-4.1 review |
| low | Manual-purge test did not check the `invalid_request` code | Asserted |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
