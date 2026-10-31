# Tasks

## 1. Crypto

- [x] 1.1 `claimcoach/corpus/crypto.py` (`KeyProvider`, `KeychainKeyProvider`, `InMemoryKeyProvider`, `Cipher`); verify `test_us_4_2_key_in_keychain`, `test_us_4_2_keychain_failure_fails_closed`
- [x] 1.2 Encrypt user-scope bodies, chunks, and vectors; verify `test_us_4_2_user_store_not_plaintext`, `test_us_4_2_wrong_key_fails_closed`

## 2. Evidence

- [x] 2.1 Record `evidence/US-4.2/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
