# Design: US-3.2 Handler-Level Redaction of Agent Tool Results

## Context

Hermes calls a plugin tool handler as `handler(args, **context)` and expects a JSON string
(PC-8). If the handler raises, Hermes returns `"Tool execution failed: <type>: <message>"` to the
model. `transform_tool_result` callbacks run after the handler; a raising callback is skipped and
the original result is used (fail-open, `model_tools._apply_transform_tool_result_hook`, PC-7).
The redactor (US-3.1) runs in the worker, not in the gateway.

## Goals / Non-Goals

**Goals:** no `claimcoach_*` result reaches the agent unredacted, with or without the hook, and
with a failing hook; a failure yields a fixed envelope, never content or exception text.

**Non-Goals:** the content of each tool's result (EPIC-9); redacting other plugins' tools.

## Decisions

1. **Redaction happens in the worker, called synchronously from the handler.** The handler runs
   the async `WorkerClient.redact()` on a dedicated thread with its own event loop, because
   Hermes may call sync handlers from a thread that already runs a loop. The wait is bounded by
   `GUARD_TIMEOUT` (180 s, enough for a cold Qwen3-8B start); the thread is not joined on
   timeout and ends with its own httpx timeout. *Alternative:* `is_async=True` handlers —
   rejected, hook callbacks are sync anyway and one mechanism serves both guards.
2. **Field-by-field JSON redaction.** Redacting the raw JSON text missed PHI after an escaped
   newline (`\nKeanu` — the `n` defeats word boundaries); found by
   `test_us_3_2_tool_results_phi_free_without_hook`. The guard decodes the result, joins every
   key and string value with a separator (`\n\x1e\n`) into one `/redact` call, splits the answer,
   and rebuilds the document. A field-count mismatch fails closed. Non-JSON text is redacted
   whole. *Alternative:* one call per field — rejected, N model calls per result.
3. **Neither guard ever raises** (review finding, high). Any failure inside redaction — worker
   error, timeout, a result over `MAX_TEXT_CHARS`, a field-count change, a pydantic
   `ValidationError` (whose message quotes its input), recursion — is caught; only its type is
   logged. The handler then returns `redaction_failed`; the hook returns `None` so Hermes keeps the
   already-redacted handler result. A handler that raises or returns a non-string →
   `internal_error`. *Alternative (first version):* let unexpected errors propagate to Hermes'
   fail-open path — rejected, Hermes quotes exception text to the agent and its logs.
4. **Fixed envelopes skip the model.** A result that is exactly a ClaimCoach envelope (known code
   and that code's fixed message) is re-serialized from the code; it cannot carry PHI. A forged
   envelope with another message is redacted like any result.
5. **The hook only touches `claimcoach_*` tools** and only string results; for anything else it
   returns `None` (no change). Its timeout is 25 s (`HOOK_TIMEOUT`), under Hermes'
   `plugins.hook_callback_timeout` (30 s), past which Hermes drops the callback and skips it for a
   while. The handler keeps 180 s for a cold model start.
7. **Numbers and keys are fields too** (review findings). A careless handler may return an MRN
   as a JSON number: numbers are redacted as text and stay numbers when unchanged. Two keys that
   redact to the same placeholder fail closed instead of silently merging.
8. **Daemon thread with a total deadline** (review finding). The redaction coroutine runs in a
   daemon thread under `asyncio.wait_for(timeout)`, so a hung call never blocks gateway shutdown.
6. **Real-Hermes probe.** `test_us_3_2_real_hermes_dispatch_is_guarded` (`@pytest.mark.hermes`)
   runs Hermes' own `handle_function_call` with ClaimCoach enabled, a live worker on 18200, and
   a leaking handler, once with ClaimCoach's hook and once with a raising hook. The offline
   tests use a replica of that dispatch that cites the Hermes source.

## Risks / Trade-offs

- [Every tool result costs a model call] → results are short; envelopes skip the call; the PHI
  model stays loaded between calls (idle unload after 10 min).
- [Worker down makes tools useless] → intended (fail closed); the envelope's fixed message tells
  the agent the feature is unavailable.
- [A result larger than one `/redact` call (200 000 characters)] → fails closed; tool results
  are summaries, far below that.
