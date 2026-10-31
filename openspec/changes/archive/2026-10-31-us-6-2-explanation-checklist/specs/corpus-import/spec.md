# Spec Delta

## Purpose

Lets a rule card list the documents a payer requires, so the diagnosis checklist can draw on it.

## ADDED Requirements

### Requirement: Rule cards may list required documents
A `required_docs` rule card MAY carry `required_documents`, a list of up to 30 entries of 1 to 200
characters (an empty list is no list); the list SHALL be stored with the card and read back
unchanged. A list on a card of any other topic SHALL fail the whole import.

#### Scenario: Required documents are stored with the card
- **WHEN** the manager imports a required_docs rule card with a list of required documents
- **THEN** the stored card reads back with the same list in the same order

#### Scenario: A list on another topic is refused
- **WHEN** a bundle holds a timely_filing rule card with required documents
- **THEN** the import fails with invalid_request and nothing is stored
