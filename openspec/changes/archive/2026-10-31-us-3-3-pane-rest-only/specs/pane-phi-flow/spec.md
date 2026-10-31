# Spec Delta

## Purpose

Defines how the desktop pane reaches case data so that PHI never passes through the Hermes agent
transcript.

## ADDED Requirements

### Requirement: Pane case actions use only plugin REST calls
The desktop pane SHALL perform every case action (create, upload, open, process) through a case
API client that wraps only `ctx.rest` on the ClaimCoach namespace, and `plugin.js` SHALL NOT use
`host.composer`, `host.request`, or any session method.

#### Scenario: Pane case actions use only plugin REST calls
- **WHEN** plugin.js is loaded with a fake ctx and host and the biller uploads a document and opens a case in the pane
- **THEN** plugin.js calls only ctx.rest endpoints
- **AND** it never accesses host.composer, host.request, or session methods

#### Scenario: Backend unavailable
- **WHEN** a case call fails or returns a malformed case ID
- **THEN** the pane shows that case work is not available and shows no backend error text

### Requirement: Case processing adds nothing to agent sessions
Processing a case from the pane SHALL NOT add messages or tool calls to any agent session, and no
ClaimCoach backend module SHALL import Hermes' session store, agent loop, tool dispatch, or
gateway transports.

#### Scenario: Case processing adds nothing to agent sessions
- **WHEN** the biller processes a case from the pane while an agent session is active
- **THEN** the agent session gains no messages or tool calls
