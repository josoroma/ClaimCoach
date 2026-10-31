# Proposal: US-3.2 Handler-Level Redaction of Agent Tool Results

## Why

The Hermes chat agent may run on a cloud model, so anything a ClaimCoach tool returns can leave
the Mac. Each handler must redact its own result (primary guard); `transform_tool_result` is
fail-open (PC-7) and may only be a second guard (SPECS.md US-3.2, PRD §7.2, BR-3).

## What Changes

- `claimcoach.agent.guard`: `redact_tool_result()` wraps a handler so its JSON string result is
  redacted through the worker's `POST /redact` before Hermes sees it; `make_hook()` /
  `register_guard_hook()` register the same redaction as the `transform_tool_result` hook for
  `claimcoach_*` tools only.
- JSON results are redacted field by field (decoded keys and string values in one worker call,
  then re-serialized). ClaimCoach's fixed error envelopes pass through without a model call.
- Fail closed: an unreachable worker, a model error, a timeout (180 s), or a redaction that loses
  a field returns the `redaction_failed` envelope. A handler that raises returns
  `internal_error`, so Hermes never quotes exception text to the agent.
- `register_tools()` registers every handler wrapped; `register_agent()` (called by
  `plugin/__init__.py`) registers the tools and the hook. `WorkerClient.redact()`.
- `create_app(..., redactor=...)` lets tests mount `/redact` over a fake PHI model.

## Capabilities

### New Capabilities
- `tool-result-guard`: redaction of agent tool results by the handler and by the hook.

### Modified Capabilities
- None (the `plugin-package` tool registration contract — names, schemas, JSON-string results —
  is unchanged).

## Impact

- The agent half now calls the worker for every non-envelope tool result; with the worker
  stopped, tools answer `redaction_failed` instead of content.
- `tests/fakes/registrar.py` (shared fake `PluginContext`), `tests/fakes/live_app.py`,
  `tests/hermes/probe_guard.py`.
