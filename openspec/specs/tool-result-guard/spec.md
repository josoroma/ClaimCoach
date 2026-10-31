# tool-result-guard Specification

## Purpose
Defines how ClaimCoach keeps PHI out of agent tool results: every handler redacts its own result
and the `transform_tool_result` hook redacts again as defense in depth.

## Requirements

### Requirement: Handlers redact their own results
Every `claimcoach_*` tool handler SHALL be registered wrapped by `redact_tool_result()`, which
redacts the handler's JSON string result through the worker's PHI redactor before returning it.
JSON results SHALL be redacted field by field and returned as JSON.

#### Scenario: Tool results are PHI-free without the hook
- **WHEN** the transform_tool_result hook is not registered and a claimcoach_* tool handler returns a result about a case containing seeded PHI
- **THEN** the returned JSON string contains none of the seeded PHI strings

### Requirement: The hook re-redacts as a second guard
The plugin SHALL register a `transform_tool_result` callback that redacts the result of every
`claimcoach_*` tool again and leaves other tools' results unchanged.

#### Scenario: The hook re-redacts
- **WHEN** a claimcoach_* tool result containing seeded PHI passes through the registered hook
- **THEN** the hook output contains none of the seeded PHI strings

#### Scenario: Other tools are untouched
- **WHEN** a tool whose name does not start with claimcoach_ passes through the hook
- **THEN** the hook returns no replacement

### Requirement: Guards fail closed
When redaction cannot complete (worker unreachable, model error, timeout, or a redaction that
does not preserve the result's fields) the guard SHALL return the `redaction_failed` envelope; a
handler that raises SHALL yield the `internal_error` envelope without the exception text.

#### Scenario: A failing hook does not expose PHI
- **WHEN** the transform_tool_result hook raises and a claimcoach_* tool result is returned to the agent
- **THEN** the agent receives the handler-redacted result, which contains none of the seeded PHI strings

#### Scenario: Worker unavailable
- **WHEN** a handler returns a result and the worker cannot be reached
- **THEN** the agent receives the redaction_failed envelope
