# Runbook: Corpus import, reindex, backup, and restore

Stories: US-4.1 (scopes, reindex, backup, restore), US-4.2 (user scope encryption, key backup),
US-4.3 (import). Rules: BR-1 (imports read a local file only), BR-5, BR-6 (user scope encrypted at rest),
BR-13.

Scopes: `global` at `<hermes root>/plugin-data/claimcoach/global/` (every profile, no PHI) and
`user` at `plugin_data_dir("claimcoach")/user/` (one profile, contains PHI, encrypted with a key in
the macOS Keychain: service `ClaimCoach user store`, account `user-store:<profile>`). Each scope
holds `corpus.sqlite3` (WAL) and its own vector index `index.sqlite3`.

Every command below also runs as `hermes claimcoach corpus <command>` once the plugin is enabled.

## Preconditions

- The worker is running for import, list, status, reindex, purge, and audit (`make start`). The
  desktop pane and the gateway always use 18200, so another port is for a scratch or test worker
  only. Such a worker needs its own `HERMES_HOME` (one data dir runs one worker), and both
  `HERMES_HOME` and `WORKER_PORT` go to these targets too; they send the port as `--port`
  (`hermes claimcoach corpus list --port 18213` outside make). The token is sent only to the port
  the launcher recorded for the running worker; any other port answers `worker_unavailable`.
  Backup, restore, and the key commands do not use the worker port.
- The `embedding` model is present (`make models-check`); import and reindex embed with it.
- The worker is **stopped** for restore (`make stop`).
- Profile names are Hermes profile names (lowercase letters, digits, `-`, `_`); a name with no
  user scope answers `profile_not_found` and creates nothing.
- Backups of the `user` scope go to encrypted storage only. They stay encrypted as stored, but
  they are case data.

## Steps

1. **Import the global corpus (US-4.3).** Write a bundle (`.yaml`, `.yml`, or `.json`, at most
   5 MiB): `items:` with `kind: rule_card | code | letter_template`; every item needs `title`,
   `body`, `source`, and `verified_on` (ISO date). Rule cards add `payer` and `topic`
   (`timely_filing`, `appeal_levels`, `required_docs`, `submission`, `corrected_claims`, `other`);
   a `required_docs`
   card may add `required_documents`, a list of up to 30 documents that becomes the diagnosis
   checklist (US-6.2; see [case-diagnosis](case-diagnosis.md)), and an `appeal_levels` card may add
   `appeal_limit_days` (1–3650 calendar days from the denial date), the appeal deadline's limit
   (US-6.3), and a `corrected_claims` card may add `remedies` (denial reason → `corrected_claim`,
   `appeal`, `either`, or `none`) and `frequency_code` (`1`, `7`, or `8`), which override
   ClaimCoach's corrected-claim table for that payer (US-7.4; see
   [appeal-drafting](appeal-drafting.md)); codes add
   `code_set` (`CARC`, `RARC`, `GROUP`) and `code`; templates add `template_id`. Then:
   `make corpus-import FILE=rules.yaml`, or in Hermes Desktop Settings → **ClaimCoach** →
   **Global corpus import** (US-10.4): pick the file, read what it holds and replaces, then press
   **Import into the global corpus** (see [desktop-pane-and-settings](desktop-pane-and-settings.md)).
   The import is all or nothing; re-importing an item with the same key replaces it. A bundle's
   text is at most 5 MiB.
2. **Reindex after an embedding-model change (US-4.1).** The worker reads `models.yaml` when it
   starts, so restart it after editing the `embedding` role (`make stop && make start`). Then
   `make corpus-status` shows
   `needs_reindex: true` when `models.yaml` names a different embedding model than the index
   was built with; searches and imports answer `index_stale` until you run
   `make corpus-reindex SCOPE=global` and, for each profile, `make corpus-reindex SCOPE=user
   PROFILE=<name>`. `needs_reindex` is also true when chunks have no vector
   (`missing_vectors`, e.g. after an interrupted write).
3. **Back up both scopes (US-4.1).** `make corpus-backup BACKUP_DIR=/Volumes/Encrypted/claimcoach`
   uses SQLite's online backup from one read snapshot, so the worker may keep running and each
   scope's index matches its database. It writes `claimcoach-corpus-<UTC stamp>/{global,
   user-<profile>}/`; a failed backup leaves no partial folder.
4. **Back up each profile's key (US-4.2).** A user-scope backup is ciphertext: without its
   Keychain key it is unrecoverable, and Keychain Access cannot export generic passwords. Run
   `make corpus-key-export PROFILE=<name> TO=/Volumes/Encrypted/claimcoach/<name>.key` (the file is
   created mode 0600 and never overwritten). Keep it with the backup, on encrypted storage only.
5. **Restore a backup (US-4.1).** First take a fresh backup (step 3), so the restore itself can be
   rolled back. Then `make stop`; on a new Mac, import each key first with
   `make corpus-key-import PROFILE=<name> FROM=<name>.key CONFIRM=yes`; then
   `make corpus-restore FROM=<backup folder> CONFIRM=yes` and `make start`. Every scope name is
   checked before anything is replaced, and each file is replaced atomically. The audit log lives
   in the user scope's database, so entries written after the backup are replaced by the backup's;
   record the restore (date, folder, approver) outside ClaimCoach.

## Verification

- Import: `make corpus-list` shows each item with its source and verified-on date; `STALE`
  marks items verified more than 180 days ago.
- Reindex: `make corpus-status` shows `needs_reindex: false` and the configured
  `embedding_model_id` for every scope.
- Backup: the backup folder holds `corpus.sqlite3` and `index.sqlite3` per scope, mode 0600.
- Key backup: `make corpus-key-export` printed `exported the user-store:<name> key`.
- Restore: `make corpus-status` shows the restored counts; a user scope with `available: false`
  is missing its Keychain item (import it with step 5) or has the wrong one. An existing store
  never gets a new key, so importing the right one always works.

## Rollback

- Import: re-importing the previous bundle reverts only the keys it contains; items that only the
  new bundle added stay. For a full rollback, restore the global scope from the backup in step 3.
- Reindex: set the previous embedding model in `models.yaml` and reindex again.
- Restore: restore the backup taken at the start of step 5.
