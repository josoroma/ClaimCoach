# Spec Delta

## Purpose

Defines the release-blocking eval of the redactor's PHI recall on the synthetic PHI set.

## ADDED Requirements

### Requirement: Recall is measured per PHI category on the synthetic set
The redaction eval SHALL send every document of the synthetic PHI set (names, DOB, MRN, member
ID, SSN, address, phone) through the running worker's redactor and SHALL count each distinct
seeded value as recalled only when it no longer occurs in the redacted text as a whole word,
ignoring case. It SHALL report recall overall and per PHI category in a typed `EvalResult`.

#### Scenario: Gate passes at or above target
- **WHEN** the redaction eval runs on the synthetic PHI set and recall is 98% or higher
- **THEN** the gate exits 0
- **AND** writes the eval JSON to `evidence/US-12.1/redaction-recall.json`

#### Scenario: Gate blocks below target
- **WHEN** the redaction eval runs and recall is below 98%
- **THEN** the gate exits non-zero
- **AND** reports recall per PHI category

### Requirement: The report names no PHI
The eval report and its terminal summary SHALL hold document IDs, categories, error codes, and
numbers only, never a seeded value or document text.

#### Scenario: Missed values are reported by category
- **WHEN** the PHI model misses every name
- **THEN** the report lists `<document id>:name` for each document and no name itself

### Requirement: A run that measures nothing does not pass
When the worker is not running or the eval set cannot be read, the eval SHALL exit 2 without
writing a report.

#### Scenario: No worker
- **WHEN** the redaction eval runs with no worker on its port
- **THEN** it exits 2 and says the worker answered `worker_unavailable`
