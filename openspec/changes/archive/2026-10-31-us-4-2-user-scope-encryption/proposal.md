# Proposal: US-4.2 User Scope Encrypted at Rest

## Why

The user scope holds PHI (BR-6, PRD §9–§10). A copied disk, a backup on unencrypted storage, or a
stray `sqlite3` session must not reveal it; reading it should need the biller's macOS login.

## What Changes

- `claimcoach/corpus/crypto.py`: `KeyProvider` protocol; `KeychainKeyProvider` (macOS Keychain via
  `/usr/bin/security`, generic password `ClaimCoach user store` / `user-store:<profile>`);
  `InMemoryKeyProvider` (test double); `Cipher` (AES-256-GCM, a fresh 96-bit nonce per value, the
  row's table and ID as associated data).
- `CorpusStore` in the user scope encrypts every document body, chunk text, and vector, and keeps
  an encrypted key-check value so a wrong key fails closed (`corpus_unavailable`).
- New dependency `cryptography`.

## Capabilities

### New Capabilities
- `corpus-encryption`: user-scope encryption at rest and the Keychain-held key.

### Modified Capabilities
- None.

## Impact

- The worker reads one Keychain item per profile; the login keychain must be unlocked (it is while
  the user is logged in). A backup of the user scope is unreadable without that Keychain item.
