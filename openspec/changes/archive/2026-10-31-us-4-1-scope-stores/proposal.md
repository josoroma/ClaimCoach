# Proposal: US-4.1 Global and User Scope Stores

## Why

PRD §9 splits the corpus into a `global` scope (code knowledge base, payer rule cards, letter
templates; no PHI; every Hermes profile on the Mac) and a `user` scope (one biller's cases; PHI;
follows the active profile). Every later corpus story (import, retrieval, retention, audit) and
every case story (EPIC-5 onward) needs these two stores to exist at the PRD paths with SQLite and a
local vector index each, and needs them never to mix.

## What Changes

- `claimcoach/corpus/paths.py`: `global_scope_dir()` = `<hermes root>/plugin-data/claimcoach/global/`,
  `user_scope_dir()` = `plugin_data_dir("claimcoach")/user/`, plus `active_profile()`,
  `profile_user_scope_dir()` and `user_scopes()` for the app-wide worker, which serves every
  profile.
- `claimcoach/corpus/types.py`: typed `CorpusScope`, `Document`, `Chunk`, `CaseRecord`, `IndexInfo`.
- `claimcoach/corpus/store.py`: `CorpusStore` — per scope a WAL SQLite database `corpus.sqlite3`
  and its own vector index `index.sqlite3` (float32 vectors, unit length), with `secure_delete`.
  The index records the embedding model ID; a different model marks it stale and refuses writes
  and searches until `reindex`.
- `claimcoach/corpus/embed.py`: `Embedder` (`/v1/embeddings` on the `embedding` role, Qwen3-
  Embedding-8B) and `embedding_model_id()` from `models.yaml`.
- `claimcoach/corpus/service.py` and worker routes `GET /corpus/status`, `POST /corpus/reindex`.
- `docs/runbooks/corpus-import-reindex-backup-restore.md`: reindex, backup, restore sections;
  Makefile `corpus-status`, `corpus-reindex`, `corpus-backup`, `corpus-restore`.
- New dependency `numpy` (vector math in the worker only).

## Capabilities

### New Capabilities
- `corpus-scopes`: scope locations, per-scope database and vector index, embedding-model pinning.

### Modified Capabilities
- None.

## Impact

- New package `claimcoach/corpus/`; the worker mounts corpus routes. The gateway imports only
  `corpus/types.py` and `corpus/paths.py` (no numpy, no SQLite; PC-4).
