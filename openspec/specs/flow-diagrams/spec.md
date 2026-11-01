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
