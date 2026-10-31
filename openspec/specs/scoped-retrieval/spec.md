# scoped-retrieval Specification

## Purpose
Defines which chunks retrieval may return for a case.

## Requirements

### Requirement: Retrieval is limited to global plus the current case
Retrieval for a case SHALL consider only global-scope chunks and user-scope chunks of that case,
and SHALL rerank the candidates with the `rerank` role (Qwen3-Reranker-8B).

#### Scenario: Another case's chunks are never retrieved
- **WHEN** retrieval runs for an explanation on case A while case B in the same user scope holds distinct seeded PHI
- **THEN** no returned chunk belongs to case B

#### Scenario: Global chunks are available to every case
- **WHEN** retrieval runs for any case while a rule card is in the global scope
- **THEN** the rule card is eligible to be returned

#### Scenario: A query without a case is invalid
- **WHEN** a retrieval query has no case ID
- **THEN** it does not validate and nothing is searched

#### Scenario: Case purged during the rerank
- **WHEN** the current case is purged while its retrieval waits on the reranker
- **THEN** none of its chunks is returned
