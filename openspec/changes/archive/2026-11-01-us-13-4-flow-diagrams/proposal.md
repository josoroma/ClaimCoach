# Proposal: US-13.4 App Flow Diagrams for Stakeholders and Users

## Why

A practice owner, a biller, and a developer each need a picture of ClaimCoach: what stays on the Mac, what happens to a case, and how one request travels (SPECS.md US-13.4).

## What Changes

- `docs/assets/flow-stakeholder.svg`: the Mac boundary with the pane, `plugin_api.py`, the worker, local models, both corpus scopes, and the agent tools inside; the Hermes chat agent, model downloads, and payers outside; a legend for PHI, no-PHI, and boundary-crossing arrows.
- `docs/assets/flow-user.svg`: the seven steps of a case with the model each uses, the manager dashboard, and v1.1 payer calls.
- `docs/assets/flow-request.svg`: a sequence diagram of `POST /process` from the pane to the model server, the sealed write, and the progress events.
- All three under **App flows** in README-DEV.md; the user and stakeholder diagrams also in README.md. `tests/test_us_13_4_flow_diagrams.py` checks content, the boundary by position, and self-containment.

## Capabilities

### New Capabilities
- `flow-diagrams`: the app flow diagrams and their checks.

### Modified Capabilities
- None.

## Impact

- Docs and tests only.
