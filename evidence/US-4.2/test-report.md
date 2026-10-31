# Test Report: US-4.2 User Scope Encrypted at Rest

Change: us-4-2-user-scope-encryption
Story: US-4.2
Verdict: pass
Coverage: 2/2 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent re-run after the post-review revision
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; `/usr/bin/security` present

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "User store files are not plaintext: Then no seeded PHI string is found" | PASS | `test_us_4_2_user_store_not_plaintext`: a case is built from a synthetic PHI document, with the patient name in the title. The test reads every file in the user-scope directory as raw bytes (database, `-wal`, `-shm`, vector index), then every file under the test root. It finds none of the seeded PHI strings (case-insensitive), both while the store is open and after it closes. The check has teeth: the store still decrypts the text and title exactly, and the encrypted index still answers a search for the case. Also: `test_us_4_2_cipher_binds_value_to_row`. `test_us_4_2_ciphertext_is_bound_to_its_case`: rows moved to another case with raw SQL raise `CorpusKeyError`. `test_us_4_2_tampered_values_fail_closed`: a short blob, or a tampered `key_check`, fails closed. `test_us_4_2_user_document_ids_are_opaque`: a file-name-like doc ID is refused. `test_us_4_2_wrong_key_fails_closed`: 503 `corpus_unavailable` |
| 2 | "The key lives in the Keychain: Then the item exists and the key is not written to any file in the plugin data dir" | PASS | `test_us_4_2_key_in_keychain`: `KeychainKeyProvider` runs against a real throwaway keychain, created with `security create-keychain` under `tmp_path`. After `user_store("biller-a", create=True)`, `security find-generic-password -s <service> -a user-store:biller-a -w` returns a 32-byte hex key. Reopening reads the same key and decrypts the case. No file under the Hermes root contains the key as raw, lowercase hex, or uppercase hex bytes. `test_us_4_2_existing_store_never_gets_a_new_key`: a store whose Keychain item is missing fails closed, the purge lists it in `skipped`, and the throwaway keychain still has no item (`security` exit 44). `test_us_4_2_key_export_and_import_round_trip`: `corpus key-export` writes a `0600` file and never overwrites it. After the item is deleted, export gives `corpus_unavailable`. `key-import` without `--confirm` is refused; with it, the key is restored and the store decrypts again. A non-hex key file is refused. Also `test_us_4_2_key_never_in_argv`, `test_us_4_2_store_key_refusals`, `test_us_4_2_keychain_failure_fails_closed[5 cases]`, `test_us_4_2_keychain_unreachable_fails_closed` |

## Evidence Commands

```bash
make evidence STORY=US-4.2
uv run pytest -m "not models" -p no:cacheprovider --no-cov -k us_4_ -v
# HERMES_HOME and MODELS_HOME pointed at a scratch directory; guard paths and dry runs only:
make corpus-key-export
make -n corpus-key-export TO=<scratch>/k.key PROFILE=biller-a
make corpus-key-import FROM=<scratch>/missing.key
make corpus-key-import FROM=<scratch>/present.key
make -n corpus-key-import FROM=<scratch>/present.key CONFIRM=yes
```

```text
tests/test_us_4_2_user_scope_encryption.py ...................           [100%]
- generated xml file: .../evidence/US-4.2/junit.xml -
====================== 19 passed, 827 deselected in 2.46s ======================

test_us_4_2_user_store_not_plaintext PASSED
test_us_4_2_wrong_key_fails_closed PASSED
test_us_4_2_cipher_binds_value_to_row PASSED
test_us_4_2_key_in_keychain PASSED
test_us_4_2_keychain_failure_fails_closed[denied|not-hex|short-key|add-lost|binary] PASSED (5)
test_us_4_2_keychain_unreachable_fails_closed PASSED
test_us_4_2_key_never_in_argv PASSED
test_us_4_2_existing_store_never_gets_a_new_key PASSED
test_us_4_2_key_export_and_import_round_trip PASSED
test_us_4_2_store_key_refusals PASSED
test_us_4_2_ciphertext_is_bound_to_its_case PASSED
test_us_4_2_tampered_values_fail_closed PASSED
test_us_4_2_user_document_ids_are_opaque PASSED
test_us_4_2_cli_uses_the_login_keychain_by_default PASSED

$ make corpus-key-export
usage: make corpus-key-export TO=<new key file> [PROFILE=<name>]
exit=2
$ make -n corpus-key-export TO=<scratch>/k.key PROFILE=biller-a
uv run python -m claimcoach.cli corpus key-export --to "<scratch>/k.key" --profile "biller-a"
$ make corpus-key-import FROM=<scratch>/missing.key
usage: make corpus-key-import FROM=<key file> CONFIRM=yes
exit=2
$ make corpus-key-import FROM=<scratch>/present.key
corpus-key-import deletes or replaces corpus data and cannot be undone; re-run with CONFIRM=yes
exit=2
$ make -n corpus-key-import FROM=<scratch>/present.key CONFIRM=yes
uv run python -m claimcoach.cli corpus key-import --from "<scratch>/present.key" --confirm
```

Artifacts: `evidence/US-4.2/junit.xml`

## Failures

None.

## Notes

- Every real Keychain call ran against a throwaway keychain file. The tests create it under
  `tmp_path`, never add it to the search list, and delete it afterwards. The user's login Keychain
  was not touched.
- `test_us_4_2_cli_uses_the_login_keychain_by_default` checks only that the CLI builds a provider
  with no keychain argument, that is, the default search list. That provider never ran against the
  login Keychain. For the same reason, `make corpus-key-export` and `make corpus-key-import` were
  run only on their guard paths and as dry runs (`make -n`). The CLI commands themselves were
  exercised in-process against the throwaway keychain.
- The SPECS.md open question (is the vector index encrypted too?) is resolved in design.md: yes,
  per row. Row 1 covers this, because the raw-byte scan includes the index file.
- Embeddings come from the fake model server. Encryption does not depend on the embedding model.
