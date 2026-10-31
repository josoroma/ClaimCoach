# Tasks

## 1. Audit

- [x] 1.1 `AuditEntry`, the append-only `audit_log`, `open_case`; verify `test_us_4_6_opening_case_writes_audit_entry`, `test_us_4_6_audit_log_append_only`
- [x] 1.2 `GET /corpus/audit`, CLI and Makefile `corpus-audit`; verify `test_us_4_6_audit_route`
- [x] 1.3 Record `evidence/US-4.6/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
