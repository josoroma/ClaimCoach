# Design: US-4.6 Audit Log of Case Access

## Context

Open questions: the entry fields, which actions besides opening a case are audited, how long
entries are kept, and whether the retention purge removes them.

## Goals / Non-Goals

**Goals:** opening a case appends an entry; entries cannot be edited or deleted through SQL; no PHI
in an entry.

**Non-Goals:** an audit viewer in the pane (US-10.x); tamper evidence against someone with write
access to the file (a hash chain is a follow-up if the Product Manager wants it).

## Decisions

1. **Fields: `seq`, `at` (UTC), `action`, `case_id`, `profile`.** The Hermes profile is the biller
   (PRD §9: one profile = one biller). No document names, text, or counts beyond the action.
2. **Audited actions:** `case_created`, `case_opened`, `document_added`, `case_closed`,
   `outcome_recorded`, `case_purged`. Retrieval inside a request is not separately audited: it
   runs only for a case the request has opened.
3. **Kept indefinitely; not purged.** Entries carry no PHI, so BR-7 does not apply, and HIPAA
   expects safeguard documentation to be kept (six years). A purge itself is audited.
4. **Append-only by trigger** in the same encrypted-at-rest user database, so the log shares the
   scope's backup and restore.

5. **Review outcomes.** A third trigger blocks `INSERT OR REPLACE` / `REPLACE INTO` over an
   existing entry; manual purges are `case_purged_on_request`, policy purges `case_purged`. Case
   routes (US-5.x) must read a case through `open_case`; `documents`, `chunks`, and `search` are
   not audited because they run only inside a request that opened the case.

## Risks / Trade-offs

- [Unbounded growth] → a few bytes per action; a retention option can be added once decided.
- [A restore replaces entries written after the backup] → the restore runbook says to record the
  restore outside ClaimCoach; keeping the log in its own file is a follow-up if wanted.
