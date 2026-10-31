# Proposal: US-3.3 PHI Flows Bypass the Agent Transcript

## Why

The Hermes agent transcript may go to a cloud model. Case uploads and case work must go
desktop pane → `plugin_api.py` → worker only, never through `host.composer`, `host.request`, or
an agent session (SPECS.md US-3.3, PRD §7.2, BR-2, PC-4).

## What Changes

- `plugin/desktop/plugin.js`: a typed (JSDoc) case API client, `createCaseApi(rest)`, whose four
  calls (`createCase`, `uploadDocument`, `getCase`, `processCase`) wrap only `ctx.rest` on this
  plugin's own namespace; `uploadCase`, `openCase`, `processCase`, `describeCase`.
- The case pane gains a file input (create case → upload → open) and a Process button. Any
  failure reads as "not available"; backend error text is never shown.
- `plugin.js` never imports `host` from the SDK and never references the composer, `request`, or
  sessions; a node test scans the source, and a recording `host` in the fake SDK proves no access.
- Python: an AST scan proves the gateway routes and the app package import none of Hermes'
  session store, agent loop, tool dispatch, or gateway transports.

## Capabilities

### New Capabilities
- `pane-phi-flow`: the desktop pane's case actions and their path to the backend.

### Modified Capabilities
- None.

## Impact

- The case routes (`/cases`, `/cases/{id}/documents`, `/cases/{id}`, `/cases/{id}/process`) are
  served by EPIC-5 (US-5.1); until then the pane shows "not available" (the gateway answers 404).
- Fake SDK `host` recorder, fake agent `sessions`, and `hooks.seed` in the fake React.
