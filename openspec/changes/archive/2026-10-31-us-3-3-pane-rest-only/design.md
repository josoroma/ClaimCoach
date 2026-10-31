# Design: US-3.3 PHI Flows Bypass the Agent Transcript

## Context

The Hermes Desktop SDK gives a plugin `ctx.rest` (its own backend namespace) and, through the
`host` export, the composer (`host.composer.insertText/setDraft/submit`), the gateway JSON-RPC
door (`host.request`), and session actions. Anything put in the composer or sent through
`host.request` can land in the agent transcript.

## Goals / Non-Goals

**Goals:** the pane's case actions provably use only `ctx.rest`; processing a case changes no
agent session.

**Non-Goals:** the case routes themselves and the case model (US-5.1); progress display from
`plugin.claimcoach.case.progress` events (US-10.1).

## Decisions

1. **One client object over `ctx.rest`.** `createCaseApi(rest)` is the only code that names case
   paths; the pane receives `rest` from `register(ctx)` and nothing else. *Alternative:* call
   `ctx.rest` inline in components — rejected, harder to prove nothing else is used.
2. **Never import `host`.** The structural guarantee is that `plugin.js` cannot reach the agent:
   the SDK import list excludes `host`, and the source (comments stripped) contains no `host`,
   `composer`, `.request(`, or `session` token. The fake SDK's `host` records every access, so a
   future import would also fail the behavior test.
3. **Case IDs are validated on the client** (`^[A-Za-z0-9_-]{1,64}$`) and encoded into paths; a
   malformed ID reads as unavailable. Uploads use `PluginRestOptions.upload` (bytes, filename,
   content type), never `ctx.files`.
4. **Errors are a state, not text.** Every failure maps to `{state: 'unavailable'}` with a fixed
   message (BR-14), the same pattern as the worker status.
5. **Backend side checked by an import allowlist** (review finding: a blocklist missed Hermes'
   59 `hermes_state_*` modules). ClaimCoach modules may import only the standard library, their
   declared dependencies, `claimcoach`, and `hermes_cli.config`, `hermes_cli.plugin_events`,
   `hermes_constants`, `plugins.plugin_storage`.
6. **No overlapping actions** (review finding). The file input is disabled while busy, Process
   switches to busy before it awaits, and only the latest action (and only while mounted) may
   update the pane.

## Risks / Trade-offs

- [Remote gateway, BR-1] (review finding) → `ctx.rest` goes to whatever gateway the Desktop app is
  connected to, and Hermes supports remote `hermes serve` gateways. This story sends no PHI yet
  (the case routes arrive with US-5.1), but the first case route must refuse uploads unless the
  gateway is the local one. Recorded as a requirement for US-5.1, not solved here.
- [Session criterion proven structurally] (review finding) → the node test and the import scan
  prove the pane cannot reach a session; no live Hermes session was counted, because there is no
  case route to call yet. US-5.1 should add a `hermes` test that counts session messages before
  and after `POST /cases/{id}/process`.

- [A later story needs a host action (toast, navigate)] → allowed actions can be added
  deliberately; the test then lists the permitted `host` members, still excluding the composer,
  `request`, and sessions.
- [The import scan misses dynamic imports] → `importlib`-style imports are not used in the
  package; the quality gate would flag a new one in review.
