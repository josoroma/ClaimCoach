# Design: US-4.1 Global and User Scope Stores

## Context

The worker is app-wide (one process for every profile, US-1.2), but the user scope follows the
active profile. Hermes' `plugin_data_dir` is `<HERMES_HOME>/plugin-data/<name>`, where a profile's
`HERMES_HOME` is `<root>/profiles/<name>` and the default profile's is the root itself.

## Goals / Non-Goals

**Goals:** PRD paths for both scopes; one WAL database and one vector index per scope; the index
pinned to an embedding model; reindex and backup procedures.

**Non-Goals:** encryption (US-4.2), import formats (US-4.3), retrieval ranking (US-4.4), any case
UI (EPIC-5).

## Decisions

1. **The worker addresses a user scope by profile name.** `profile_user_scope_dir(profile)` maps
   `default` to `<root>/plugin-data/claimcoach/user` and `<name>` to
   `<root>/profiles/<name>/plugin-data/claimcoach/user`, the same path Hermes' `plugin_data_dir`
   gives under that profile (tested against a fake `plugin_storage` that follows the profile).
   Names are validated (`[A-Za-z0-9_-]{1,64}`), so a request can never point the worker at an
   arbitrary directory. *Alternative:* the gateway sends a path — rejected, the worker would have
   to trust a path from the request.
2. **Vector index = its own SQLite file per scope**, attached to the scope's connection. Vectors
   are float32 blobs normalized to unit length; search is a numpy dot product over the candidate
   set. The user scope is only ever searched one case at a time (US-4.4), so brute force stays
   small; the global corpus is thousands of chunks. *Alternatives:* `sqlite-vec` (needs loadable
   extensions, which macOS' Python may not allow) and FAISS (a native dependency and an index
   format that cannot be encrypted per row for US-4.2) — rejected for v1.
3. **The index records `embedding_model_id`** (the `embedding` role's `model_dir` in
   `models.yaml`, e.g. `Qwen3-Embedding-8B-4bit-DWQ`) and the vector dimension. When the
   configured model differs, `IndexInfo.needs_reindex` is true and adding or searching vectors
   raises `IndexStaleError` (`index_stale`, 409) until `reindex` re-embeds every chunk and records
   the new ID. A dimension mismatch on insert is refused the same way.
4. **`secure_delete=ON` and `foreign_keys=ON`** on both files: deleted PHI pages are zeroed
   (US-4.5 relies on it) and chunks cascade with their document. Orphaned vectors (a crash between
   the two files' commits) are removed on open.
5. **Embeddings via OpenAI `/v1/embeddings`**, queries prefixed with the Qwen3-Embedding instruction
   line. Whether the configured server exposes that endpoint is a real-model concern
   (`@pytest.mark.models`); offline tests use the fake server's deterministic embedding.

6. **Review outcomes.** Reads never create a user scope (`create=True` is for case creation only),
   so a mistyped profile leaves nothing behind; profile names are Hermes' `PROFILE_ID_RE`. Store
   opens and the purge run off the event loop (thread pool / `asyncio.to_thread`) behind one lock.
   `missing_vectors` forces a reindex; a backup copies both files from one read snapshot; restore
   validates every name first and replaces files atomically. *Alternative:* create on demand —
   rejected, a typo would mint a Keychain item and a ghost scope that every purge then visits.

## Risks / Trade-offs

- [`mlx_lm.server` in the default `models.yaml` may not serve `/v1/embeddings`] → the request
  shape is the OpenAI standard; the embedding role's `command` is user-editable (US-2.1), and the
  real-model check is a follow-up under `make test-models`.
- [Brute-force search grows linearly with the global corpus] → acceptable at v1 sizes; the store
  hides the search behind `search()` so an ANN index can replace it.
