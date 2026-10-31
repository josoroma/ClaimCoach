# delivery-evidence Specification

## Purpose
Defines where and how ClaimCoach records delivery evidence, operations runbooks, and architecture
decisions, so every story's acceptance can be traced from criterion to command output.

## Requirements

### Requirement: Evidence template follows the OhMyOrch report contract
`evidence/TEMPLATE/test-report.md` SHALL contain `Change:`, `Story:`, `Verdict:`, `Coverage:`, an
`## Acceptance Criteria Evaluated` table whose rows quote the criterion and carry `PASS`, `FAIL`, or
`UNVERIFIED` with the command and output used, an `## Evidence Commands` section, and a
`## Failures` section. A criterion that was not exercised SHALL be `UNVERIFIED`, never `PASS`.

#### Scenario: Report created from the template validates
- **WHEN** a story's report is created from the template and the report validator runs on it
- **THEN** the validator accepts a report that quotes each criterion with PASS, FAIL, or UNVERIFIED and the command and output

#### Scenario: Inconsistent verdict rejected
- **WHEN** a report says `Verdict: pass` but a criterion row is `FAIL`
- **THEN** the validator rejects it

#### Scenario: Every delivered story has a valid report
- **WHEN** the validator runs over `evidence/US-*/test-report.md`
- **THEN** every report passes and has a sibling `junit.xml`

### Requirement: Required runbooks exist with the four sections
`docs/runbooks/` SHALL contain the install-enable, worker-start-stop-health,
model-download-convert, corpus-import-reindex-backup-restore, upgrade, troubleshooting, phi-purge,
and phi-incident runbooks, each with Preconditions, Steps, Verification, and Rollback headings.

#### Scenario: Runbook lint
- **WHEN** the runbook-lint test runs
- **THEN** every required runbook exists and has the four headings

### Requirement: ADR-0001 records the worker decision
`docs/adr/0001-worker-sidecar.md` SHALL record the PRD §7.9 worker decision with Status, Context,
Decision, and Consequences sections.

#### Scenario: ADR present
- **WHEN** the developer opens ADR-0001
- **THEN** it records the worker decision with status, context, decision, and consequences
