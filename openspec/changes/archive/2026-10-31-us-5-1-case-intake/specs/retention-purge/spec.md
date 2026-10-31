# Spec Delta

## Purpose

Extends the retention purge to the source files and derived items EPIC-5 attaches to a case.

## MODIFIED Requirements

### Requirement: Expired case content is purged
The worker SHALL purge, at start and every 6 hours, the documents, chunks, vectors, and case items
(attached source files and anything derived from them) of every case closed more than
`retention_days` (default 90) ago, in every profile's user scope.

#### Scenario: Expired source documents are purged
- **WHEN** the purge job runs on a case closed 91 days ago with the default retention setting
- **THEN** the case's source documents, their chunks, and their vectors are deleted

#### Scenario: A case inside the retention period is kept
- **WHEN** the purge job runs on a case closed 89 days ago with the default retention setting
- **THEN** its documents, chunks, and vectors remain

#### Scenario: Expired attached files are purged
- **WHEN** the purge job runs on a case closed 91 days ago that holds only attached source files
- **THEN** the files are deleted and the case lists no source documents
