# Review: US-4.1

Change: us-4-1-scope-stores
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-2-user-scope-encryption. Cross-cutting findings from the US-4.3/4.4 and US-4.5/4.6 reviews that touch this change are included.
Verdict: pass after fixes; one risk carried as UNVERIFIED (real embedding server)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Store opens and the startup purge ran sync Keychain/SQLite work on the event loop; a locked keychain could stall startup past the launcher's 15 s | Store-opening routes are plain `def` (thread pool); `RetentionJob` runs `purge_all` in `asyncio.to_thread`; a lock guards store opening; `test_us_4_5_purge_runs_off_the_event_loop` |
| medium | `status()` failed entirely when one profile's store did not open | Per-profile `available: false` (typed `ScopeStatus`, `index` optional); `test_us_4_1_status_reports_a_profile_that_does_not_open` |
| medium | Any well-formed profile name created a scope, database, and Keychain item (even `GET /corpus/audit`); names were looser than Hermes' | Reads never create (`user_store(..., create=False)` → `profile_not_found`, 404); `ProfileName` is Hermes' `PROFILE_ID_RE`; `test_us_4_1_reads_never_create_a_profile`, `test_us_4_3_cli_worker_commands` (typo creates nothing) |
| medium | Default `embedding` command (`mlx_lm.server`) may not serve `/v1/embeddings` | Not fixed here: needs a real model run. Kept as the design's risk and UNVERIFIED in evidence; proposed as a follow-up (models-marked smoke test, or a ClaimCoach embedding server) |
| low | Reindex not serialized against writes | `asyncio.Lock` around import and reindex in `CorpusService` |
| low | Chunks without vectors went unnoticed; backup copied the two files at different moments | `IndexInfo.missing_vectors` forces `needs_reindex`; backup copies both files from one read snapshot; `test_us_4_1_missing_vectors_force_reindex`, `test_us_4_1_backup_is_one_snapshot_and_refusal_creates_nothing` |
| low | Restore deleted before copying, failed mid-way on a bad folder name; partial backups left behind; refused backup created `global/` | Names validated first, staged copy + atomic rename, partial backup removed, nothing created on refusal; `test_us_4_1_restore_validates_first_and_fails_safe` |
| low | Lifespan teardown skipped shutdowns when a background task had died | `gather(return_exceptions=True)` in a `try/finally` that always runs shutdowns; `test_us_4_1_lifespan_survives_a_dead_task` |
| low | Worker derived the Hermes root from an unchecked `--data-dir` | Corpus mounted only for `<root>/plugin-data/claimcoach`; `test_us_4_1_worker_main_mounts_the_corpus` |
| low | Runbook did not say to restart the worker after a `models.yaml` change | Runbook step 2 |
| low | Reindex test could not tell new vectors from kept ones | `test_us_4_1_reindex_writes_new_vectors` (override vector, similarity 1.0 after reindex) |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
