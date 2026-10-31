# Spec Delta

## Purpose

Defines when and how case content is purged from the user scope and what survives.

## ADDED Requirements

### Requirement: Expired case content is purged
The worker SHALL purge, at start and every 6 hours, the documents, chunks, and vectors of every case
closed more than `retention_days` (default 90) ago, in every profile's user scope.

#### Scenario: Expired source documents are purged
- **WHEN** the purge job runs on a case closed 91 days ago with the default retention setting
- **THEN** the case's source documents, their chunks, and their vectors are deleted

#### Scenario: A case inside the retention period is kept
- **WHEN** the purge job runs on a case closed 89 days ago with the default retention setting
- **THEN** its documents, chunks, and vectors remain

### Requirement: Outcomes survive de-identified
A purged case's outcome SHALL remain and SHALL contain no PHI.

#### Scenario: Outcomes survive the purge de-identified
- **WHEN** the outcome of a purged case is read
- **THEN** it is still present and contains no seeded PHI string

### Requirement: Retention period is configurable
The purge SHALL use the profile's `retention_days` setting.

#### Scenario: Retention period is configurable
- **WHEN** the retention setting is changed to 30 days and the purge job runs on a case closed 31 days ago
- **THEN** the case's source documents are deleted

### Requirement: Manual single-case purge needs confirmation
`POST /corpus/purge` with a `case_id` SHALL purge that case only when `confirm` is true.

#### Scenario: Manual purge without confirmation
- **WHEN** a single-case purge is requested without `confirm: true`
- **THEN** nothing is deleted and the answer is `invalid_request`

### Requirement: An untrusted retention setting never shortens retention
When a profile's config cannot be read or its `retention_days` is invalid, the purge SHALL skip
that profile for this run and report it as skipped; other settings SHALL NOT affect
`retention_days`.

#### Scenario: Invalid retention setting
- **WHEN** a profile's `retention_days` is invalid and the purge job runs on a case closed 91 days ago
- **THEN** the case is kept and the profile is listed as skipped
