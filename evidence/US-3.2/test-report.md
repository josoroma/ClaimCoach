# Test Report: US-3.2 Handler-Level Redaction of Agent Tool Results

Change: us-3-2-tool-result-guard
Story: US-3.2
Verdict: pass
Coverage: 3/3 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), run after implementation and independent review
Environment: macOS (Darwin 27.2.0, Apple Silicon M3 Pro, 36 GiB); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Tool results are PHI-free without the hook: Then the returned JSON string contains none of the seeded PHI strings" | PASS | `test_us_3_2_tool_results_phi_free_without_hook`: every tool's `handle` is patched to return the seeded case document (a buggy handler); tools are registered with `register_tools` and **no** hook; each registered handler returns JSON whose summary has `[NAME]` placeholders, keeps `CO-197`, and contains none of the seeded strings. Redaction goes through the real worker `POST /redact` on a loopback socket (uvicorn thread) backed by the fake PHI model. `test_us_3_2_every_registered_handler_is_guarded`: every handler registered by `plugin/__init__.py`'s path is wrapped |
| 2 | "The hook re-redacts as a second guard: Then the hook output contains none of the seeded PHI strings" | PASS | `test_us_3_2_hook_re_redacts`: the registered `transform_tool_result` callback, called with Hermes' payload keys and an unredacted case result for three documents, returns JSON with none of the seeded strings. `test_us_3_2_hook_leaves_other_tools_alone`: non-`claimcoach_` tools get `None`. `test_us_3_2_real_hermes_dispatch_is_guarded` (real Hermes `model_tools.handle_function_call`, ClaimCoach enabled, live worker on 18200): result PHI-free, 1 hook registered |
| 3 | "A failing hook does not expose PHI: Then the result the agent receives is the handler-redacted result and contains none of the seeded PHI strings" | PASS | `test_us_3_2_failing_hook_does_not_expose_phi`: hook scrubber raises; a dispatch replica citing Hermes v0.22.5 fails open and returns the handler-redacted result (PHI-free, `[NAME]` present). `test_us_3_2_real_hermes_dispatch_is_guarded`: the same through **real** Hermes after replacing the hook list with a raising callback → `failing_hook` result PHI-free with `[NAME]` |

## Evidence Commands

```bash
make evidence STORY=US-3.2
uv run pytest -m hermes -k us_3_2 --no-cov -v
```

```text
====================== 21 passed, 693 deselected in 4.59s ======================
tests/test_us_3_2_tool_guard.py::test_us_3_2_real_hermes_dispatch_is_guarded PASSED
```

Artifacts: `evidence/US-3.2/junit.xml`

## Failures

None.

## Notes

- Found while testing: redacting the raw JSON text missed PHI after an escaped newline (the `n`
  of `\\n` defeats word boundaries). The guard now redacts decoded keys and string values in one
  worker call (design decision 2); `test_us_3_2_json_results_are_redacted_field_by_field`.
- Fail-closed paths: unreachable worker, timeout, lost field → `redaction_failed`; handler
  exception → `internal_error` without its text.
- `hermes plugins validate` required `provides_hooks: [transform_tool_result]` in `plugin.yaml`
  (`test_us_1_1_hermes_validate_accepts_package`).
- After independent review: the guard never raises (an oversize result or a validation error
  used to escape with a PHI preview in its message; `test_us_3_2_oversize_result_fails_closed_
  without_quoting_it`); JSON numbers are redacted (`test_us_3_2_numeric_identifiers_are_redacted`);
  colliding keys fail closed; the hook's timeout (25 s) is under Hermes' 30 s hook timeout and a
  failing hook redaction leaves the handler result (`test_us_3_2_hook_whose_redaction_fails_keeps_
  the_handler_result`); a stale token with the worker down fails closed; the default path through
  `register_agent` is exercised with leaking handlers.
