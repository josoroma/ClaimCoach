# Review: US-4.2

Change: us-4-2-user-scope-encryption
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31; reviewed together with us-4-1-scope-stores
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The runbook's key backup ("Keychain Access → Export") is impossible for generic passwords, so a lost Mac meant unrecoverable case data | `hermes claimcoach corpus key-export` / `key-import` (file mode 0600, never overwritten; import needs `--confirm`, read back and compared); Makefile `corpus-key-export`, `corpus-key-import`; runbook steps 4–5; `test_us_4_2_key_export_and_import_round_trip` (throwaway keychain) |
| medium | `key_for` created a new key for an existing store whose item was missing, blocking the later import of the real key | `KeyProvider.key_for(account, create=...)`: a key is created only for a brand-new store; `test_us_4_2_existing_store_never_gets_a_new_key` (no Keychain item written) |
| low | Plaintext `doc_id` could carry PHI; associated data did not bind a value to its case | User-scope `doc_id` must be opaque; associated data is `<table>:<case_id>:<row>`; `test_us_4_2_user_document_ids_are_opaque`, `test_us_4_2_ciphertext_is_bound_to_its_case` |
| low | A truncated blob or tampered `key_check` raised `ValueError` (500) instead of failing closed | Both raise `CorpusKeyError` (`corpus_unavailable`); `test_us_4_2_tampered_values_fail_closed` |
| info | Docstring said the key is "compared" after the add | Wording fixed: every write is read back and the stored key is the one used; `store_key(replace=True)` does compare |

## Re-verification

`make verify` → exit 0: ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, the offline pytest
suite and node tests at 100% line and branch coverage, evidence-check (`ok` for US-1.1 to US-4.6,
OhMyOrch accepted every report), 2 gate self-tests. Evidence re-recorded by the independent
`story-tester` after the fixes.
