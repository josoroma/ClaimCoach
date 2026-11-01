# Spec Delta

## Purpose

The diagrams no longer draw their own background (US-13.7) or define their own dark colors
(US-13.8 does, from the theme), and the redrawn request diagram's loop holds only the gateway's
polling.

## REMOVED Requirements

### Requirement: The diagrams are self-contained and readable in light and dark themes
**Reason**: It asked each diagram to paint its own background; US-13.7 makes the canvas transparent, and US-13.8 takes light and dark colors from the theme.
**Migration**: Restated below as "The diagrams are self-contained and shown in the guide"; transparency is in `diagram-design`, colors in `diagram-theme`.

### Requirement: The developer diagram follows one request
**Reason**: Its loop held the worker's model call and sealed write as if they repeated; in the redrawn sequence diagram they happen once, and only the gateway's polling repeats.
**Migration**: Restated below as "The developer diagram follows one extraction", which also pins each message to the lifelines that exchange it.

## ADDED Requirements

### Requirement: The developer diagram follows one extraction
`docs/assets/flow-request.svg` SHALL draw one extraction as messages between the lifelines that
exchange them, in order: the gateway route and the worker route with the per-launch token;
`JobStarted` back to the pane; the worker's call to the model server, started on first use under
the memory guard, its answer, and the sealed `put_case_item` write with its audit entry to the user
corpus; then one loop, until the job ends, in which the gateway long-polls the job's events and
publishes `plugin.claimcoach.case.progress` to the pane; then the pane reads the case through the
gateway. Every route, event name, and port it draws SHALL be the code's.

#### Scenario: The developer diagram follows one extraction
- **WHEN** docs/assets/flow-request.svg is viewed
- **THEN** it shows one extraction from the pane through plugin_api and the worker to the model server and the user corpus, each message between the lifelines that exchange it, in order
- **AND** only the gateway's polling for progress events repeats, until the job ends

### Requirement: The diagrams are self-contained and shown in the guide
Every SVG under `docs/assets/` SHALL be self-contained, switch to light colors under
`prefers-color-scheme: light`, and appear as an image under App flows in README-DEV.md.

#### Scenario: The diagrams are self-contained and shown in the guide
- **WHEN** every diagram under docs/assets/ is parsed
- **THEN** it is a valid SVG with a title and no script, external reference, or embedded image
- **AND** README-DEV.md shows every diagram
