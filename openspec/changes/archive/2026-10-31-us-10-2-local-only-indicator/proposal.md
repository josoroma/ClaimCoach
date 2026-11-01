# Proposal: US-10.2 Local-Only Statusbar Indicator

## Why

PRD §7 and §11: a statusbar item tells the biller ClaimCoach is local-only, and shows when richer
agent access is on (PRD §7.2). US-3.5 registered the item on `STATUSBAR_AREAS.right` with a boolean
state; US-10.2 asks for an explicit, JSDoc-typed state model and the local-only default.

## What Changes

- `IndicatorState` (`'local-only' | 'richer-access'`) and `indicatorView(state)` (label and title)
  in `plugin.js`; `LocalOnlyIndicator` holds an `IndicatorState`, starting `local-only`.
- `loadIndicatorState(rest)` reads `/settings`; anything but an explicit `true` is `local-only`.
- The item carries `data-state` so the host (and tests) can tell the two states apart.

## Capabilities

### New Capabilities
- `local-only-indicator`: the statusbar item's typed state and its local-only default.

### Modified Capabilities
- None (`richer-agent-access` keeps its requirement that the item shows when richer access is on).

## Impact

- `plugin.js` only; no backend change.
