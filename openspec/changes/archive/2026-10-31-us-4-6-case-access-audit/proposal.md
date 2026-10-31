# Proposal: US-4.6 Audit Log of Case Access

## Why

PRD §10 lists an audit log of case access among the practice's documented safeguards.

## What Changes

- `claimcoach/corpus/types.py`: `AuditAction`, `AuditEntry`, `AuditResponse`.
- `audit_log` table in each user-scope database, append-only (SQLite triggers abort `UPDATE` and
  `DELETE`). `CorpusStore` appends an entry on every case-level action: created, opened, document
  added, closed, outcome recorded, purged.
- `CorpusStore.open_case()` is the only way to read a case record and always audits.
- Worker `GET /corpus/audit`, CLI `corpus audit`, Makefile `corpus-audit`.

## Capabilities

### New Capabilities
- `case-audit`: audited actions, entry fields, append-only storage.

### Modified Capabilities
- None.

## Impact

- SPECS.md keeps US-4.6 NEEDS CLARIFICATION; the field set and retention below are defaults.
