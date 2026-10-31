# Test Report: US-4.5 Retention Auto-Purge of Source Documents

Change: us-4-5-retention-purge
Story: US-4.5
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Expired source documents are purged: Then the case's source documents, their chunks, and their vectors are deleted" | PASS | `test_us_4_5_expired_documents_purged`: a case closed 91 days ago, default retention, more than 1 chunk. `purge_all` reports `("default", ["old"], 1)` with chunks == vectors > 1. Raw-file counts are `(0, 0, 0)` and both `-wal` files are 0 bytes. `purged_at` is set, and re-running is a no-op. `test_us_4_5_worker_runs_scheduled_purge`: the worker lifespan's `RetentionJob` purges a case closed 100 days ago. `test_us_4_5_case_inside_retention_kept`: a case closed 89 days ago, and an open case, stay at `(1, 1, 1)`. Also: `test_us_4_5_close_times_compare_in_utc` (a −05:00 close time is compared in UTC); `test_us_4_5_closing_again_keeps_the_retention_clock`; `test_us_4_5_blocked_checkpoint_is_reported` (`checkpoint()` returns False with a warning while a reader pins the WAL, then True); `test_us_4_5_storage_error_in_one_profile_does_not_stop_others` (profile `b` is listed in `skipped`, and `default` is still purged); `test_us_4_5_purge_runs_off_the_event_loop`; `test_us_4_5_manual_purge_requires_confirm` (no `confirm` → 422, unknown case → 404 `case_not_found`) |
| 2 | "Outcomes survive the purge de-identified: Then the outcome is still present and contains no seeded PHI string" | PASS | `test_us_4_5_outcomes_survive_deidentified`: a case built from a synthetic PHI document, closed 120 days ago, with outcome `OVERTURNED`. After the purge, `store.outcome("won")` is still `OVERTURNED`, and its JSON contains no seeded PHI string. The `outcomes` table columns are exactly `case_id, outcome, recorded_at` |
| 3 | "Retention period is configurable: Then the case's source documents are deleted" | PASS | `test_us_4_5_retention_configurable`: the default profile's `config.yaml` sets `retention_days: 30`, and profile `b` sets 365. Only `c31` (closed 31 days ago) is purged to `(0, 0, 0)`. `c29` and `b`'s `c200` stay at `(1, 1, 1)`. `test_us_4_5_untrusted_retention_skips_the_profile[0, thirty, None, 5000]`: an invalid `retention_days` skips the profile (`reports == []`, `skipped == ["default"]`) and a 91-day-old case is kept, both for `purge_all` and for a named purge. `test_us_4_5_unrelated_invalid_setting_keeps_retention`: an invalid sibling setting does not reset 365 days to 90. Also `test_us_4_5_profile_settings_read` |

## Evidence Commands

```bash
make evidence STORY=US-4.5
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models make corpus-purge PROFILE=default CASE=c1
```

```text
tests/test_us_4_5_retention_purge.py ....................                [100%]
- generated xml file: .../evidence/US-4.5/junit.xml -
====================== 20 passed, 826 deselected in 6.31s ======================

test_us_4_5_expired_documents_purged PASSED
test_us_4_5_case_inside_retention_kept PASSED
test_us_4_5_outcomes_survive_deidentified PASSED
test_us_4_5_retention_configurable PASSED
test_us_4_5_untrusted_retention_skips_the_profile[0] PASSED
test_us_4_5_untrusted_retention_skips_the_profile[thirty] PASSED
test_us_4_5_untrusted_retention_skips_the_profile[None] PASSED
test_us_4_5_untrusted_retention_skips_the_profile[5000] PASSED
test_us_4_5_unrelated_invalid_setting_keeps_retention PASSED
test_us_4_5_manual_purge_requires_confirm PASSED
test_us_4_5_worker_runs_scheduled_purge PASSED
test_us_4_5_close_times_compare_in_utc PASSED
test_us_4_5_closing_again_keeps_the_retention_clock PASSED
test_us_4_5_blocked_checkpoint_is_reported PASSED
test_us_4_5_storage_error_in_one_profile_does_not_stop_others PASSED
test_us_4_5_purge_runs_off_the_event_loop PASSED

$ make corpus-purge PROFILE=default CASE=c1
corpus-purge deletes or replaces corpus data and cannot be undone; re-run with CONFIRM=yes
make: *** [corpus-purge] Error 2
```

Artifacts: `evidence/US-4.5/junit.xml`

## Failures

None.

## Notes

- Behaviour changed after review: an unreadable config, or an invalid `retention_days`, now skips
  the profile for that run instead of falling back to 90 days (design.md decision 3,
  `load_retention_days`). Row 3 covers this.
- US-8.1, a listed dependency, is not delivered. Outcomes are recorded with `store.record_outcome`
  and the `CaseOutcome` enum.
- The scheduled purge was exercised inside the worker's lifespan in-process (ASGI app). The real
  worker process and its 6-hour timer were not observed.
- `make corpus-purge` was run only to check its `CONFIRM=yes` guard. A real purge needs a running
  worker.
- Embeddings come from the fake model server. The purge does not depend on the embedding model.
