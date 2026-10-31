# Runbook: PHI purge

Status: **skeleton** — US-4.5 fills manual purge and verification. Rules: BR-7 (source documents
auto-purge, default 90 days after case close; outcomes kept de-identified), BR-13.

## Preconditions

- Written approval from the practice's privacy officer for any manual purge outside the schedule.
- The worker is running (purge goes through it so the audit log records it, US-4.6).

## Steps

1. US-4.5: run the purge for expired source documents.
2. US-4.5: purge a single case on request.

## Verification

- US-4.5: the case's source documents are gone from the `user` scope and the index; its
  de-identified outcome remains.

## Rollback

- A purge cannot be undone by design. Restoring from a backup reintroduces PHI and needs the same
  approval as the purge.
