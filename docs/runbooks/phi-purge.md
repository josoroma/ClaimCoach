# Runbook: PHI purge

Story: US-4.5 (retention auto-purge), with US-4.6 (every purge is audited). Rules: BR-7 (case
content auto-purges a configurable period after case close, default 90 days; outcomes are kept
de-identified), BR-13, BR-14.

What a purge deletes: every document of the case in the user scope (source documents and anything
derived from them: extracted fields, drafts, notes), their chunks, and their vectors. What stays:
the case row (ID and dates), its outcome (`overturned`, `upheld`, or `written_off`, nothing
free-text), and its audit entries (`case_purged` for the policy, `case_purged_on_request` for an
approved manual purge). Deleted pages are zeroed (`secure_delete`) and both WAL files are
truncated afterwards.

The worker purges on its own at start and every 6 hours, for every profile, using that profile's
**Settings → Plugins → ClaimCoach → retention_days** (`plugins.entries.claimcoach.settings` in the
profile's `config.yaml`; a missing value is 90). A purge never trusts a setting it cannot read:
when the config is unreadable or `retention_days` is invalid, that profile is **skipped** (listed
under `skipped`) and retried on the next run, so a typo can never shorten retention.

## Preconditions

- Written approval from the practice's privacy officer for any manual purge outside the schedule.
- The worker is running (`make start`); the purge goes through it so the audit log records it.
- The profile's login keychain is unlocked (you are logged in to the Mac).

## Steps

1. **Run the scheduled purge now** for every profile: `make corpus-purge`, or one profile:
   `make corpus-purge PROFILE=<name>`.
2. **Purge one case on request** (approved in writing), whatever its retention date:
   `make corpus-purge PROFILE=<name> CASE=<case id> CONFIRM=yes`.
3. **Expire backups.** A purge reaches only the live store. Delete corpus backups
   (`corpus-import-reindex-backup-restore.md`, step 3) older than the retention period, and for a
   manual purge every backup that still holds the case.

## Verification

- The purge prints, per profile, the purged case IDs and the documents, chunks, and vectors
  deleted; `skipped` is empty (otherwise fix that profile's config or Keychain item and re-run).
- `make corpus-audit PROFILE=<name> CASE=<case id>` ends with a `case_purged` (or, for step 2,
  `case_purged_on_request`) entry.
- `make corpus-status` shows the lower document and chunk counts; the case's outcome remains.

## Rollback

- A purge cannot be undone by design. Restoring from a backup
  (`corpus-import-reindex-backup-restore.md`, step 5) reintroduces the PHI and needs the same
  approval as the purge; the next scheduled purge removes it again unless the retention setting
  changed.
