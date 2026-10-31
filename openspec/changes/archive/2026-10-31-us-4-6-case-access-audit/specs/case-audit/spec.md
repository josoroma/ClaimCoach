# Spec Delta

## Purpose

Defines the audit log of case access in the user scope.

## ADDED Requirements

### Requirement: Case access is audited
Opening a case SHALL append an audit entry with the time, action, case ID, and profile, and so
SHALL creating, adding a document, closing, recording an outcome, and purging. Entries SHALL carry
no PHI.

#### Scenario: Opening a case writes an audit entry
- **WHEN** the biller opens a case in the user scope
- **THEN** an audit entry is appended for that case

### Requirement: The audit log is append-only
The audit log SHALL reject updates and deletes, and the retention purge SHALL NOT remove entries.

#### Scenario: Audit entries cannot be changed
- **WHEN** an `UPDATE` or `DELETE` is run on the audit log
- **THEN** SQLite aborts it and the entries are unchanged
