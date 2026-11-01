# Spec Delta

## Purpose

Defines the manager-approved export of de-identified case/outcome pairs for a future fine-tune of
the classifier: when it runs, what it holds, and where it goes.

## ADDED Requirements

### Requirement: Export requires manager approval
A fine-tune export SHALL run only for a request carrying an approval with a manager's name and
`approved: true`; any other request SHALL be refused with `export_not_approved` before any
outcome is read, and no export file SHALL be written. Every approved export SHALL be appended to
an owner-only approval log, and an export whose log line cannot be written SHALL be removed.

#### Scenario: Export requires manager approval
- **WHEN** de-identified case/outcome pairs exist and an export is requested without manager approval
- **THEN** no export file is written

#### Scenario: Every approved export is logged
- **WHEN** the manager approves an export
- **THEN** the export's file name, record count, profiles, approver, and time are appended to the approval log

### Requirement: Exported pairs contain no PHI
Each exported record SHALL be built only from an outcome's de-identified snapshot (rule-card payer
name, codes, payment statuses, denial reason, appeal likelihood, outcome; no dollar amount) of a
profile that shares its outcomes; a record the PHI regex validators match SHALL be withheld.

#### Scenario: Exported pairs contain no PHI
- **WHEN** the export runs with manager approval
- **THEN** the export file contains none of the seeded PHI strings

#### Scenario: Only labeled outcomes of sharing profiles are exported
- **WHEN** outcomes without a current diagnosis, outcomes recorded before facts were kept, and outcomes of a profile that does not share exist
- **THEN** none of them is exported and the unlabeled ones are counted
