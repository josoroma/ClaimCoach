# Runbook: Corpus import, reindex, backup, and restore

Status: **skeleton** — US-4.1 fills reindex and backup, US-4.3 fills import. Rules: BR-5, BR-6
(user scope encrypted at rest), BR-13.

Scopes: `global` at `~/.hermes/plugin-data/claimcoach/global/` (all profiles, no PHI) and `user` at
`plugin_data_dir("claimcoach")/user/` (one profile, contains PHI).

## Preconditions

- The worker is stopped for backup and restore, so SQLite WAL files are consistent.
- Backups of the `user` scope are stored on encrypted storage only (it contains PHI).

## Steps

1. US-4.3: import the global corpus with provenance (`hermes claimcoach corpus import`).
2. US-4.1: reindex after an embedding-model change.
3. US-4.1: back up both scope folders.
4. US-4.1: restore a scope folder from backup.

## Verification

- US-4.1: the index records the current embedding model ID and retrieval returns results.

## Rollback

- Restore the previous scope folder from the backup taken in step 3.
