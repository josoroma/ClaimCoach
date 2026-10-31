# Review: US-3.2

Change: us-3-2-tool-result-guard
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | Only `WorkerError` and timeouts were caught: a result over 200 000 characters raised a pydantic `ValidationError` whose message quotes the head and tail of the text, which Hermes returns to the agent and logs | `guard_text` never raises (any failure → fallback, type logged); size checked before the call; `test_us_3_2_oversize_result_fails_closed_without_quoting_it`, `test_us_3_2_non_string_results_are_handler_bugs` |
| medium | JSON numbers were never redacted (`{"mrn": 4454893}` passed) | Numbers are fields; unchanged ones stay numbers; `test_us_3_2_numeric_identifiers_are_redacted` |
| low | Hook timeout 180 s exceeded Hermes' 30 s hook timeout (callback dropped and suppressed) | `HOOK_TIMEOUT` 25 s; a failing hook redaction returns `None` (handler result kept); `test_us_3_2_hook_whose_redaction_fails_keeps_the_handler_result` |
| low | Non-daemon executor thread; httpx timeout per phase, not total | Daemon thread, `asyncio.wait_for` total deadline, 1 s join grace; `test_us_3_2_a_blocked_redaction_thread_is_abandoned` |
| low | Keys redacting to the same placeholder silently merged | Fails closed; `test_us_3_2_keys_that_redact_alike_fail_closed` |
| low | "Unreachable" test only covered a missing token | Parametrized with a stale token and a closed port |
| low | Marker-only check of the `register_agent` path | Default-scrubber test now drives `register_agent` with leaking handlers and checks every handler and the hook |
| low (cross-story) | Snake_case labels not matched | Fixed in US-3.1 validators |
| info | `test_us_2_4_conversion_holds_back_model_loads` failed during review | Port 18202 was held by the tester's live worker at that moment; passes alone and in `make check` with nothing else running |

## Re-verification

`make check` → exit 0 (710 pytest + 27 node, 100%). `pytest -m hermes` → 8 passed, including
`test_us_3_2_real_hermes_dispatch_is_guarded` (real `handle_function_call`, with and without a raising hook).

`make verify` → exit 0 (ruff, ruff format, biome, mypy --strict ×2, tsc --checkJs, 710 pytest +
27 node tests at 100% line and branch coverage, evidence-check incl. OhMyOrch for all 15 stories,
2 gate self-tests).
