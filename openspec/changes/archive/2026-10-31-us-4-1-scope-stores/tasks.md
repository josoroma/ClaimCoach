# Tasks

## 1. Paths and types

- [x] 1.1 `claimcoach/corpus/paths.py` and `types.py`; verify `test_us_4_1_global_scope_under_root`, `test_us_4_1_user_scope_follows_profile`, `test_us_4_1_invalid_profile_refused`

## 2. Store and index

- [x] 2.1 `claimcoach/corpus/store.py` with WAL database and vector index per scope; verify `test_us_4_1_each_scope_own_db_and_index`
- [x] 2.2 Record the embedding model ID per index; a change forces reindex; verify `test_us_4_1_model_change_forces_reindex`
- [x] 2.3 `claimcoach/corpus/embed.py` (`Embedder`); verify `test_us_4_1_embedder_*`

## 3. Worker and operations

- [x] 3.1 `GET /corpus/status`, `POST /corpus/reindex`; verify `test_us_4_1_status_route`, `test_us_4_1_reindex_route`
- [x] 3.2 Runbook reindex/backup/restore sections and Makefile targets; verify `test_us_1_5_runbooks_have_sections`, `test_us_4_1_backup_restore_round_trip`
- [x] 3.3 Record `evidence/US-4.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
