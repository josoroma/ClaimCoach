# Spec Delta

## Purpose

Defines where ClaimCoach's two corpus scopes live and how each stores documents, chunks, and
vectors.

## ADDED Requirements

### Requirement: Global scope resolves under the Hermes root
The global store SHALL live at `get_default_hermes_root()/plugin-data/claimcoach/global/` whatever
profile is active.

#### Scenario: Global scope resolves under the Hermes root
- **WHEN** the global store path is resolved under any active Hermes profile
- **THEN** it is `get_default_hermes_root()/plugin-data/claimcoach/global/`

### Requirement: User scope follows the active profile
The user store SHALL live at `plugin_data_dir("claimcoach")/user/` of the active profile, and the
worker SHALL resolve the same directory from a validated profile name.

#### Scenario: User scope follows the active profile
- **WHEN** the user store path is resolved under profiles A and B
- **THEN** each is that profile's `plugin_data_dir("claimcoach")/user/` and the two differ

#### Scenario: Invalid profile name
- **WHEN** the worker is asked for the user scope of a profile name containing `/` or `..`
- **THEN** it refuses with `invalid_request` and opens nothing

### Requirement: Each scope has its own database and vector index
Each scope SHALL have its own WAL SQLite database and its own vector index file, and the index
SHALL record the embedding model it was built with (Qwen3-Embedding-8B by default).

#### Scenario: Each scope has its own database and vector index
- **WHEN** both scopes are initialized and opened
- **THEN** each has its own WAL `corpus.sqlite3` and `index.sqlite3`, and each index records the Qwen3-Embedding-8B model ID

#### Scenario: A model change forces reindex
- **WHEN** the embedding model in `models.yaml` changes after the index was built
- **THEN** the index reports `needs_reindex`, searches and inserts fail with `index_stale`, and `reindex` re-embeds every chunk under the new model ID

### Requirement: Reads never create a user scope
Status, audit, purge, reindex, and retrieval SHALL open only an existing user scope; only case
creation SHALL create one. A profile name SHALL match Hermes' `PROFILE_ID_RE`.

#### Scenario: Mistyped profile
- **WHEN** a read names a profile that has no user scope
- **THEN** it answers `profile_not_found` and no directory, database, or Keychain item is created

#### Scenario: One profile does not open
- **WHEN** the status is read while one profile's store cannot open
- **THEN** that profile is reported `available: false` and the other scopes are reported normally
