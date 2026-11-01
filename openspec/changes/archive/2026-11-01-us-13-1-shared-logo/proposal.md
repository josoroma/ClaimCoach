# Proposal: US-13.1 Shared ClaimCoach Logo on the Plugin Pages

## Why

ClaimCoach's pages in Hermes Desktop carry only text headings, and the repository has no mark for
its READMEs. One logo, drawn the same everywhere, lets a biller recognize the pane, the manager
dashboard, and the settings page, and gives README.md and README-DEV.md the same mark
(SPECS.md US-13.1).

## What Changes

- `plugin/assets/claimcoach-logo.svg`: the logo, a self-contained SVG (title, viewBox, plain
  `rect`/`path` shapes, no scripts, external references, or images). It ships in the plugin
  package; `make validate` accepts it.
- `plugin/desktop/plugin.js`: `LOGO` (the file's shapes, attribute for attribute) and
  `ClaimCoachLogo`, an `aria-hidden` inline SVG, drawn at the start of the case pane's and the
  settings page's `ClaimCoach` heading and the dashboard's `ClaimCoach dashboard` heading.
- Tests: the file's contract in Python; the pages, the match with the file, and the screen-reader
  behavior under `node --test`.

## Capabilities

### New Capabilities
- `shared-logo`: the logo file and its use on the plugin pages.

### Modified Capabilities
- None.

## Impact

- `plugin.js` gains one component and one constant; two existing assertions read the heading's
  text from its last child. No REST, worker, or storage change.
