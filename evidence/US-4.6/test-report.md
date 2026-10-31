# Test Report: US-4.6 Audit Log of Case Access

Change: us-4-6-case-access-audit
Story: US-4.6
Verdict: pass
Coverage: 1/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

The scenario has two rows. Row 1 opens the case through `CorpusStore.open_case`, which is the only
case-open path in the codebase today. Row 2 is a biller opening a case from the pane or a case
route, which does not exist yet (US-5.1).

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Opening a case writes an audit entry: Then an audit entry is appended for that case" (`CorpusStore.open_case`) | PASS | `test_us_4_6_opening_case_writes_audit_entry`: in profile `biller-a`, opening `case-1` grows the case's audit log by exactly 1. The new entry is `(CASE_OPENED, "case-1", "biller-a")`, with `seq` and `at` greater than the previous entry's. `test_us_4_6_audit_log_append_only[UPDATE…, DELETE…, INSERT OR REPLACE…, REPLACE INTO…]`: all four raw SQL statements fail with `append-only`, and the log is unchanged. `test_us_4_6_every_case_action_audited_without_phi`: the case's entries are, in order, `case_created`, `document_added`, `case_closed`, `case_opened`, `outcome_recorded`, `case_purged_on_request` (a confirmed manual purge). The entries survive the purge and contain no seeded PHI. `test_us_4_6_audit_route`: `GET /corpus/audit` through the client returns the entries for one case and for the whole profile `biller-b` |
| 2 | "Opening a case writes an audit entry: Then an audit entry is appended for that case" (the biller opens the case from the pane / a case route) | UNVERIFIED | Not exercised: no case route or pane exists yet (US-5.1). See Notes |

## Evidence Commands

```bash
make evidence STORY=US-4.6
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
```

```text
tests/test_us_4_6_case_access_audit.py .......                           [100%]
- generated xml file: .../evidence/US-4.6/junit.xml -
====================== 7 passed, 839 deselected in 0.83s =======================

test_us_4_6_opening_case_writes_audit_entry PASSED
test_us_4_6_every_case_action_audited_without_phi PASSED
test_us_4_6_audit_log_append_only[UPDATE audit_log SET action = 'case_created'] PASSED
test_us_4_6_audit_log_append_only[DELETE FROM audit_log] PASSED
test_us_4_6_audit_log_append_only[INSERT OR REPLACE INTO audit_log VALUES (1, '2026-01-01', 'case_created', 'x', 'p')] PASSED
test_us_4_6_audit_log_append_only[REPLACE INTO audit_log VALUES (2, '2026-01-01', 'case_created', 'x', 'p')] PASSED
test_us_4_6_audit_route PASSED
```

Artifacts: `evidence/US-4.6/junit.xml`

## Failures

None.

## Notes

- SPECS.md keeps US-4.6 NEEDS CLARIFICATION. This run tested the defaults recorded in
  `openspec/changes/us-4-6-case-access-audit/design.md`:
  - Fields: `seq`, `at`, `action`, `case_id`, `profile`.
  - Audited actions: `case_created`, `case_opened`, `document_added`, `case_closed`,
    `outcome_recorded`, `case_purged` (policy purge), and `case_purged_on_request` (manual,
    confirmed purge).
  - Entries are kept indefinitely and are not removed by the retention purge.
  - The log is append-only, enforced by triggers that block `UPDATE`, `DELETE`, and replace.
  The Product Manager may still change these.
- Row 2: the worker exposes `GET /corpus/audit` but no case-open route. Today,
  `CorpusStore.open_case` is what writes `case_opened`. design.md decision 5 says case routes
  (US-5.x) must read a case through `open_case`. Retest this row when US-5.1 lands.
- Append-only only blocks changes made through SQL. Someone with write access to the file can still
  tamper with it; a hash chain is a follow-up (design.md Non-Goals).
- `make corpus-audit` was not run: it needs a running worker.
