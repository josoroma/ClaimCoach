# Design: US-4.5 Retention Auto-Purge of Source Documents

## Context

The purge runs in the app-wide worker, which has no Hermes `load_config_readonly()`, yet the
retention period is a per-profile Hermes plugin setting (`retention_days`, US-1.1). US-8.1, a
listed dependency, is not delivered.

## Goals / Non-Goals

**Goals:** the three scenarios; a purge that leaves no recoverable PHI page; an audited, manual
single-case purge for the runbook.

**Non-Goals:** the outcome route and UI (US-8.1); purging the global scope (no PHI).

## Decisions

1. **What is purged: all case content.** A purge deletes every user-scope document of the case
   (source documents and anything derived from them: extracted fields, drafts, notes), their
   chunks, and their vectors. Only the case row (IDs and dates), its outcome, and its audit entries
   remain. *Alternative:* source documents only — rejected: derived drafts carry the same PHI.
2. **Outcomes are de-identified by construction.** The `outcomes` table holds the `CaseOutcome`
   enum (`overturned`, `upheld`, `written_off`, from US-8.1) and a timestamp, nothing free-text,
   so there is nothing to redact when the case is purged.
3. **Retention per profile from its own config, failing closed.** `load_retention_days(home)`
   reads `<profile home>/config.yaml` → `plugins.entries.claimcoach.settings.retention_days` and
   validates that value on its own. A missing value is the default (90); an unreadable file or an
   invalid value skips the profile for this run (`PurgeResponse.skipped`), so a typo can never
   shorten retention and the purge retries 6 hours later. *Alternative (first version, rejected in
   review):* fall back to the defaults like `load_settings`, which turned a 365-day setting into 90.
4. **Eligibility:** a case with `closed_at <= now - days` that still has content. Re-running is a
   no-op. Content added to a closed case after its purge is purged on the next run.
5. **No lingering pages.** `secure_delete=ON` (US-4.1) zeroes freed pages; after deleting, the
   store runs `wal_checkpoint(TRUNCATE)` on both files so old page images do not stay in the WAL.
6. **Schedule:** `RetentionJob` purges every profile's user scope at worker start and every 6
   hours; one profile's failure (e.g., a locked Keychain) is logged by type and does not stop the
   others. A manual `POST /corpus/purge` runs the same policy now; with `case_id` it purges that
   case immediately and requires `confirm: true` (privacy-officer approval, runbook).
7. **Every purge is audited** (`case_purged`, US-4.6).

8. **Review outcomes.** The purge runs in `asyncio.to_thread`; stored timestamps are UTC so text
   order is time order; re-closing keeps the first close date; a blocked WAL checkpoint is logged
   and retried; one profile's storage error skips only that profile.

## Risks / Trade-offs

- [A purge cannot be undone] → by design; the runbook's rollback is a backup restore, which needs
  the same approval.
- [Worker not running for days] → purge runs at the next start; retention is a maximum after
  close, enforced on the next run.
- [Backups keep purged content] → the phi-purge runbook expires backups older than the retention
  period, and every backup that holds a manually purged case.
