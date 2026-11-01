# Proposal: US-9.4 The /denial Slash Command

## Why

PRD §7 lists a `/denial` slash command so a biller can start denial work from the chat. SPECS.md
left its behavior open ("open the pane, list open cases, summarize a case by ID?"); this change
decides it (design decision 1) and registers it.

## What Changes

- `agent/commands.py`: `/denial` with no argument (or one that is not a case ID) answers a fixed,
  PHI-free guide: create the case and add documents in the ClaimCoach pane, run `/denial <case
  ID>`, ask about codes and payers. `/denial <case ID>` answers the case's summary as text,
  rendered from the guarded `claimcoach_case_summary` handler's result (US-9.2).
- `register_agent` registers it with `ctx.register_command("denial", …, args_hint="[case ID]")`.
- `make agent-denial [CASE=…]` runs the command handler against the running worker.

## Capabilities

### New Capabilities
- `denial-command`: the `/denial` slash command.

### Modified Capabilities
- None.

## Impact

- SPECS.md US-9.4 moves from NEEDS CLARIFICATION to done with the decision recorded here.
