# corpus-encryption Specification

## Purpose
Defines how the user corpus scope is encrypted at rest and where its key is kept.

## Requirements

### Requirement: User store files are not plaintext
Every user-scope file (database, WAL, vector index) SHALL contain no PHI from stored case content
when read as raw bytes. Document bodies, chunk text, and vectors SHALL be AES-256-GCM encrypted.

#### Scenario: User store files are not plaintext
- **WHEN** a user-scope store containing a case with seeded PHI is read as raw bytes
- **THEN** no seeded PHI string is found

#### Scenario: Wrong key fails closed
- **WHEN** the user store is opened with a different key
- **THEN** opening fails with `corpus_unavailable` and nothing is decrypted

### Requirement: The key lives in the Keychain
The user-store key SHALL be a 256-bit key held in the macOS Keychain as a generic password and
SHALL NOT be written to any file in the plugin data dir.

#### Scenario: The key lives in the Keychain
- **WHEN** the user store has been initialized and the Keychain is queried for the ClaimCoach store item
- **THEN** the item exists and the key is not written to any file in the plugin data dir

#### Scenario: Keychain failure
- **WHEN** the Keychain cannot be read
- **THEN** the store does not open and the error is `corpus_unavailable`

### Requirement: The key can be backed up and never replaced silently
An existing user store SHALL never get a new key; `corpus key-export` SHALL write a profile's key
to a new owner-only file and `corpus key-import --confirm` SHALL put it back into the Keychain.

#### Scenario: Restored store without its key
- **WHEN** a user store exists but the Keychain has no item for it
- **THEN** opening fails with `corpus_unavailable` and no Keychain item is written

#### Scenario: Key backup round trip
- **WHEN** a profile's key is exported, deleted from the Keychain, and imported with `--confirm`
- **THEN** the store opens again and decrypts its cases
