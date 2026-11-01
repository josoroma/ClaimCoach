# Spec Delta

## Purpose

The registry no longer has a `rerank` role, and an older file that has one still loads.

## MODIFIED Requirements

### Requirement: Every PRD role is registered
The default `models.yaml` SHALL load into the typed `ModelRegistry` and SHALL contain the roles
extraction, phi_detection, classification, embedding, explanation, drafting, and transcription,
and no conversion recipe. A file missing any role SHALL fail validation.

#### Scenario: Every PRD role is registered
- **WHEN** the default models.yaml is loaded into the typed ModelRegistry model
- **THEN** it contains all seven roles and no rerank role

#### Scenario: Missing role rejected
- **WHEN** a models.yaml omits the drafting role
- **THEN** loading fails with a validation error naming `roles`

## ADDED Requirements

### Requirement: An older registry still loads
Loading a `models.yaml` SHALL drop a `rerank` role and an `acquire.convert` command, written by a
version before US-14.1, without rewriting the file; any other unknown role or command SHALL still
fail validation.

#### Scenario: An existing models.yaml still loads
- **WHEN** the worker loads a models.yaml written before this change, with a rerank role and a conversion command
- **THEN** it loads without them and every other role is unchanged
- **AND** the file is not rewritten
