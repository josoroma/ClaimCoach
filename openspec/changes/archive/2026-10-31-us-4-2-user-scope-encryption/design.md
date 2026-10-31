# Design: US-4.2 User Scope Encrypted at Rest

## Context

SQLCipher would encrypt whole pages but needs a native build of SQLite that neither the Hermes
venv nor the worker venv has. The user scope is small (one biller's cases) and is read one case at
a time (US-4.4).

## Goals / Non-Goals

**Goals:** no PHI string in any user-scope file's raw bytes (database, WAL, index); the key only in
the Keychain; a wrong or missing key fails closed.

**Non-Goals:** hiding row counts, timestamps, or case IDs (not PHI); encrypting the global scope (no
PHI by definition).

## Decisions

1. **Row-level AES-256-GCM, not page-level.** Every PHI-bearing column (document title, text and
   metadata; chunk text; vectors) is a `nonce || ciphertext` blob. Associated data binds a blob to
   its table and row ID, so a blob copied onto another row does not decrypt. Plaintext columns are
   IDs, kinds, and timestamps only. *Alternative:* SQLCipher — rejected (native build, and the
   gateway's Hermes venv cannot install it).
2. **Open question resolved: the vector index is encrypted too.** Embeddings can be inverted to
   approximate their text, so user-scope vectors are encrypted per row. Retrieval decrypts only the
   current case's vectors, which US-4.4 needs anyway.
3. **Key in the macOS Keychain through `/usr/bin/security`** with fixed argv, no shell, and
   `stdin=DEVNULL` for reads. The add goes through `security -i` with the command on stdin, so the
   key never appears in a process listing; `security -i` exits 0 even when a command fails, so
   the key is read back and compared before use. Exit status 44 means "not found" and creates a
   key; any other failure is `corpus_unavailable`. *Alternative:* the `keyring` package — rejected,
   an extra dependency for one generic password.
4. **One key per profile**, account `user-store:<profile>`, so billers on one Mac do not share a key.
5. **Key check:** the store keeps an encrypted constant in `meta`; opening with a different key
   raises `CorpusKeyError` before any case is read.
6. **Tests use a throwaway keychain** (`security create-keychain` under `tmp_path`, never added to
   the search list) for the real Keychain path, and `InMemoryKeyProvider` everywhere else.

7. **Review outcomes.** `KeyProvider.key_for(account, create=...)`: a key is created only for a
   brand-new store, so an existing store whose item is missing fails closed and the real key can
   still be imported. Keychain Access cannot export generic passwords, so `key-export` /
   `key-import` (0600 file, never overwritten; import needs `--confirm` and is read back) are the
   backup path. Associated data is `<table>:<case_id>:<row>` and user-scope document IDs must be
   opaque, so neither a moved row nor a filename-as-ID leaks or misattributes PHI.

## Risks / Trade-offs

- [Losing the Keychain item makes the user scope unreadable] → the backup runbook says to back up
  the Keychain item (Keychain Access export) alongside the scope folder.
- [Row-level encryption leaks row counts and sizes] → not PHI; accepted.
