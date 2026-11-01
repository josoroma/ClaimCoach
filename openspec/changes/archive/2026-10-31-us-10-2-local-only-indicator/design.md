# Design: US-10.2 local-only statusbar indicator

## Context

`LocalOnlyIndicator` (US-3.5) polls `GET /settings` every 15 s and renders "Local-only" or
"Local-only · richer agent access on". Its state is a bare boolean.

## Goals / Non-Goals

Goals: a typed state model with two named states and the local-only default; the same text.

Non-Goals: showing worker health in the statusbar (the pane and settings page do); a click action.

## Decisions

1. **Two named states, local-only first.** `IndicatorState = 'local-only' | 'richer-access'`; the
   first render, a failed read, and any value but an explicit `true` are `local-only`. Both
   states say ClaimCoach runs on local models only: richer access changes what the agent may be
   given later, not where models run. Rejected: an `unavailable` state when the backend half is
   off (models never leave the Mac either way, so the indicator stays true to its name).
2. **`indicatorView` is pure.** The label and title come from the state alone, so every state is
   tested without a renderer.

## Risks / Trade-offs

- [A 15 s poll can show the old state briefly after the setting changes] → unchanged from US-3.5;
  the settings page reflects the change at once.
