# scoped-retrieval Specification

## Purpose
Defines which chunks retrieval may return for a case.

## Requirements

### Requirement: The index search is limited to global plus the current case
A search of a scope's vector index SHALL read, in the user scope, only the vectors and chunks of
the one case it names, filtered in SQL before anything is decrypted; a user-scope search or chunk
read without a case SHALL be refused, and a global-scope search with one SHALL be refused. Corpus
import SHALL keep embedding chunks into the index.

#### Scenario: Another case's chunks are never retrieved
- **WHEN** case B's chunk is the exact nearest neighbour of a search for case A in the same user scope
- **THEN** no returned chunk belongs to case B

#### Scenario: Global chunks are available to every case
- **WHEN** a rule card is in the global scope and any case searches the global index
- **THEN** the rule card is returned

#### Scenario: A query without a case is invalid
- **WHEN** a user-scope search or chunk read names no case
- **THEN** it is refused and nothing is read

#### Scenario: A purged case returns no chunks
- **WHEN** a case is purged after a search returned its chunk IDs
- **THEN** reading those chunks returns nothing

#### Scenario: The corpus index is kept
- **WHEN** a corpus bundle is imported
- **THEN** its chunks are embedded and stored in the global vector index
