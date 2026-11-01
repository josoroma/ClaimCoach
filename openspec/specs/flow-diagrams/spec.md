# flow-diagrams Specification

## Purpose
Defines ClaimCoach's flow diagrams: what each shows and the rules every diagram file follows.

## Requirements

### Requirement: The stakeholder diagram shows the PHI boundary
`docs/assets/flow-stakeholder.svg` SHALL draw the pane, `plugin_api.py`, the worker, the local models, both corpus scopes, and the agent tools inside the Mac boundary, and the Hermes chat agent outside it, receiving only case IDs, codes, payer names, and redacted summaries, by a no-PHI arrow from the agent tools.

#### Scenario: The stakeholder diagram shows the PHI boundary
- **WHEN** docs/assets/flow-stakeholder.svg is viewed
- **THEN** it shows the Mac boundary with the pane, plugin_api, the worker, the local model servers, and the two corpus scopes inside it
- **AND** the Hermes chat agent receives only case IDs, codes, payer names, and redacted summaries

### Requirement: The user diagram follows a case from upload to outcome
`docs/assets/flow-user.svg` SHALL draw the seven case steps in order with the model each uses, and each model named SHALL be one of `models.yaml`'s folders.

#### Scenario: The user diagram follows a case from upload to outcome
- **WHEN** docs/assets/flow-user.svg is viewed
- **THEN** it shows upload or paste, extraction and confirmation, diagnosis, drafting, edit and export, and the outcome, with the model each step uses

### Requirement: The developer diagram follows one request
`docs/assets/flow-request.svg` SHALL draw one extraction in order: the gateway route, the worker route with the per-launch token, `JobStarted`, then a loop in which the gateway long-polls the job's events and publishes `plugin.claimcoach.case.progress` while the worker starts the model, calls it, and stores the result; then the pane reads the case. Every route, event name, and port it draws SHALL be the code's.

#### Scenario: The developer diagram follows one request
- **WHEN** docs/assets/flow-request.svg is viewed
- **THEN** it shows one extraction from the pane through plugin_api and the worker to the model server and the user corpus, in order
- **AND** the job's progress events repeat while the job runs

### Requirement: The diagrams are self-contained and readable in light and dark themes
Every SVG under `docs/assets/` SHALL be self-contained, draw its background first and over its whole viewBox, give every class it styles a dark rule under `prefers-color-scheme: dark`, and appear as an image under App flows in README-DEV.md.

#### Scenario: The diagrams are self-contained and readable in light and dark themes
- **WHEN** every diagram under docs/assets/ is parsed
- **THEN** it is a valid SVG with a title and no script, external reference, or embedded image
- **AND** it draws its own background and switches its colors for a dark color scheme
- **AND** README-DEV.md shows every diagram
