# Proposal: US-7.3 No Send or Submit Anywhere

## Why

PRD §5 makes submitting appeals or claims a non-goal; PRD §6 story 4 and §10 say a draft is never
auto-sent and there is no send or submit button anywhere (BR-4). With drafting and export in place
(US-7.1, US-7.2), the absence of any send path must be checked, not assumed, so a later change
cannot add one unnoticed.

## What Changes

- A pane test that registers `plugin.js` with a fake `ctx`, collects every contribution and
  settings page, renders each (and the case pane in every state, a draft included), and fails on
  any control or contribution whose label, title, or ID offers to send, submit, fax, e-mail,
  transmit, or upload to a payer.
- A route-table test that enumerates the gateway router and the worker app with every optional
  part mounted: no route name or path is a send verb; the route set is pinned, so a new route
  fails until this test is reviewed and updated; the routes that carry case content are exercised
  end to end while every socket connect is recorded, and all of them are loopback.
- A source test: no module of the app package imports a mail, FTP, or raw HTTP client, and HTTP
  clients are created only in the reviewed loopback modules.
- BR-4 cited in the module docstrings of `plugin.js`, `api/routes.py`, `worker/case_routes.py`,
  and `letters/`.

## Capabilities

### New Capabilities
- `no-send-submit`: the guarantee that ClaimCoach has no control or route that sends a draft or
  case content to a payer or any non-loopback destination.

### Modified Capabilities
- None.

## Impact

- Tests and docstrings only; no runtime behavior changes.
- A future route or contribution has to update the pinned set on purpose.
