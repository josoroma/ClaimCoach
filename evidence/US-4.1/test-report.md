# Test Report: US-4.1 Global and User Scope Stores

Change: us-4-1-scope-stores
Story: US-4.1
Verdict: pass
Coverage: 3/4 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

Scenario 3 has two rows. Row 3 covers the per-scope database and index, with the fake
OpenAI-compatible server doing the embedding. Row 4 covers a real Qwen3-Embedding-8B run, which did
not happen (see Notes).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Global scope resolves under the Hermes root: Then it is get_default_hermes_root()/plugin-data/claimcoach/global/" | PASS | `test_us_4_1_global_scope_under_root[default, a, b]`: with a fake Hermes that switches profile, `global_scope_dir()` is `<root>/plugin-data/claimcoach/global` for all three profiles, `hermes_root() == root`, mode `0700`. `test_us_4_1_global_scope_under_root_outside_hermes`: `HERMES_HOME=<tmp>/profiles/a` still resolves to `<tmp>/plugin-data/claimcoach/global`. `test_us_4_1_worker_main_mounts_the_corpus`: the worker mounts the corpus with `root` = the Hermes root only for a `<root>/plugin-data/claimcoach` data dir, and does not mount it for any other dir |
| 2 | "User scope follows the active profile: Then each resolves to that profile's plugin_data_dir(\"claimcoach\")/user/ and the two paths differ" | PASS | `test_us_4_1_user_scope_follows_profile`: for profiles `a`, `b`, and `default`, `user_scope_dir()` equals the fake `plugin_storage.plugin_data_dir("claimcoach") / "user"`, the worker's `profile_user_scope_dir(profile)` gives the same path, and all 3 paths differ. `test_us_4_1_invalid_profile_refused[6 names]` and `..._by_routes`: names that do not match Hermes' `PROFILE_ID_RE` are refused, 422 `invalid_request`, nothing created. `test_us_4_1_reads_never_create_a_profile`: `user_store`, `audit`, and `retriever` for `typo` raise `ProfileNotFoundError`; no `profiles/` folder and no key are created |
| 3 | "Each scope has its own database and vector index: Then each scope has its own WAL SQLite database and its own vector index built with Qwen3-Embedding-8B" (store and index, fake embedding server) | PASS | `test_us_4_1_each_scope_own_db_and_index`: 4 distinct files (database + index for each scope), each `0600` with `PRAGMA journal_mode` = `wal`. Each index records an `embedding_model_id` containing `Qwen3-Embedding-8B`, with `needs_reindex` false and 1 vector. The global store holds only `rule_card:aetna`, and the user store only `case-1`. `test_us_4_1_model_change_forces_reindex`: an index built under `Old-Embedding` raises `IndexStaleError` until `POST /corpus/reindex`. `test_us_4_1_reindex_writes_new_vectors`: after reindex, the stored vector is the new model's (cosine 1.0). `test_us_4_1_missing_vectors_force_reindex`: deleting the vectors gives `missing_vectors == 1`, `needs_reindex` true. `test_us_4_1_status_reports_a_profile_that_does_not_open`: a profile whose key is missing shows `available: false`. Also `test_us_4_1_backup_is_one_snapshot_and_refusal_creates_nothing`, `test_us_4_1_restore_validates_first_and_fails_safe`, `test_us_4_1_backup_restore_round_trip` |
| 4 | "Each scope has its own database and vector index: Then each scope has its own WAL SQLite database and its own vector index built with Qwen3-Embedding-8B" (vectors from a real Qwen3-Embedding-8B server) | UNVERIFIED | Not exercised: there is no `@pytest.mark.models` test for US-4.1, and no real embedding server was started. See Notes |

## Evidence Commands

```bash
make evidence STORY=US-4.1
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
# HERMES_HOME and MODELS_HOME pointed at a scratch directory for all of these:
make help | grep corpus
make -n corpus-reindex SCOPE=global
make -n corpus-reindex SCOPE=user PROFILE=biller-a
make corpus-reindex SCOPE=bad
make corpus-reindex
uv run python -m claimcoach.cli corpus backup --to <scratch>/backup
find <scratch>/hermes <scratch>/backup
```

```text
- generated xml file: .../evidence/US-4.1/junit.xml -
====================== 40 passed, 806 deselected in 1.13s ======================

test_us_4_1_global_scope_under_root[default] PASSED
test_us_4_1_global_scope_under_root[a] PASSED
test_us_4_1_global_scope_under_root[b] PASSED
test_us_4_1_user_scope_follows_profile PASSED
test_us_4_1_each_scope_own_db_and_index PASSED
test_us_4_1_model_change_forces_reindex PASSED
test_us_4_1_reads_never_create_a_profile PASSED
test_us_4_1_status_reports_a_profile_that_does_not_open PASSED
test_us_4_1_missing_vectors_force_reindex PASSED
test_us_4_1_reindex_writes_new_vectors PASSED
test_us_4_1_backup_is_one_snapshot_and_refusal_creates_nothing PASSED
test_us_4_1_restore_validates_first_and_fails_safe PASSED
test_us_4_1_worker_main_mounts_the_corpus PASSED
test_us_4_1_lifespan_survives_a_dead_task PASSED

$ make help | grep corpus
  corpus-status      Show both corpus scopes: paths, counts, encryption, index embedding model
  corpus-reindex     Re-embed a scope after a model change: make corpus-reindex SCOPE=global|user
  corpus-backup      Back up both scopes (online, encrypted as stored): make corpus-backup [BACKUP_DIR=d]
  corpus-restore     Replace the scopes from a backup (worker stopped): make corpus-restore FROM=d CONFIRM=yes
  corpus-key-export  Write a profile's store key to a new 0600 file: make corpus-key-export TO=f [PROFILE=p]
  corpus-key-import  Put a backed-up key into the Keychain: make corpus-key-import FROM=f CONFIRM=yes
  (plus corpus-import, corpus-list, corpus-purge, corpus-audit)

$ make -n corpus-reindex SCOPE=global
uv run python -m claimcoach.cli corpus reindex --scope global
$ make -n corpus-reindex SCOPE=user PROFILE=biller-a
uv run python -m claimcoach.cli corpus reindex --scope user --profile "biller-a"
$ make corpus-reindex SCOPE=bad
Makefile:292: *** usage: make corpus-reindex SCOPE=<global|user> [PROFILE=<name>].  Stop.
exit=2
$ make corpus-reindex
Makefile:292: *** usage: make corpus-reindex SCOPE=<global|user> [PROFILE=<name>].  Stop.
exit=2

$ uv run python -m claimcoach.cli corpus backup --to <scratch>/backup   (empty HERMES_HOME)
error: no corpus scope to back up
exit=2
$ find <scratch>/hermes <scratch>/backup
<scratch>/hermes
<scratch>/backup
<scratch>/hermes/plugin-data
<scratch>/hermes/plugin-data/claimcoach
```

Artifacts: `evidence/US-4.1/junit.xml`

## Failures

None.

## Notes

- Row 4: every offline test embeds with the fake model server. The index records the configured
  `embedding` role's `model_dir` (`Qwen3-Embedding-8B-4bit-DWQ`), so the model ID is checked, but
  no real Qwen3-Embedding-8B vectors were produced. design.md (Risks) notes that the default
  `mlx_lm.server` command may not serve `/v1/embeddings`. That needs a real-model follow-up under
  `make test-models`.
- `make corpus-reindex SCOPE=global` was only dry-run (`make -n`). A real run needs a running
  worker, which was not started.
- The CLI's refused backup still creates a folder. The library-level guarantee holds:
  `test_us_4_1_backup_is_one_snapshot_and_refusal_creates_nothing` calls `backup(root, …)` with an
  explicit root and creates nothing, and the global scope folder is no longer created. But
  `python -m claimcoach.cli corpus backup` in an empty scratch `HERMES_HOME` still leaves an empty
  `<HERMES_HOME>/plugin-data/claimcoach/`. The cause: `cli.py` calls `corpus.paths.hermes_root()`,
  which calls `claimcoach.paths.app_data_dir()`, and that creates `<root>/plugin-data/claimcoach`.
  The folder holds no data, and no Gherkin criterion covers this, so it is not a FAIL. A CLI-level
  test would catch it.
- No real `~/.hermes` data, login Keychain, or model download was touched.
