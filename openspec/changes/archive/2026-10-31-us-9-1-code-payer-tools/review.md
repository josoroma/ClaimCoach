# Review: US-9.1

Change: us-9-1-code-payer-tools
Reviewer: independent `story-reviewer` agent (read-only, given the change names and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the four EPIC-9 changes
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| low | `code_keys` stripped leading zeros (`016` → `CARC/16`) while `CodeEntry.key` keeps the code as imported (`CARC/016`): a zero-padded entry could never be explained | Codes keep their digits as typed; the lookup tries the other zero paddings of a numeric CARC (`_spellings`) and answers with the entry as imported. `test_us_9_1_zero_padded_codes_are_one_code` (stored `016` asked `16`/`CO-016`, stored `16` asked `016`, stored `7` asked `007`); `test_us_9_1_code_shapes` updated |
| low | (shared, see US-9.2) `run_blocking` ran the tool call on a new thread without the caller's context | Fixed in `run_blocking` for every tool and the guard; regression test in US-9.2 |
| nit | Task 1.1 named a test that does not exist (`test_us_9_1_unknown_code_and_payer`) | Task names the real tests |

Also checked by the reviewer and found sound: loopback only, `trust_env=False`; arguments validated with `extra="forbid"` and never echoed; every handler registered behind `redact_tool_result`; worker 422s are the envelope; `code_not_found` and `payer_not_found` relayed with matching 404s; bounded waits (`TOOL_TIMEOUT` 65 s, under Hermes' tool timeout); the 4000-character cap keeps every result inside one `/redact` call; the reason code's own entry is required; routes pinned in `test_us_7_3`; `TOOL` checked by make and `ARGS` passed through the environment.

## Re-verification

See the EPIC-9 `make verify` result recorded in `us-9-4-denial-command/review.md`.
