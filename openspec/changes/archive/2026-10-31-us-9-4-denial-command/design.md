# Design: US-9.4 the /denial slash command

## Context

Hermes v0.22.5 `register_command(name, handler, description, args_hint)` registers `/name`; the
handler is `fn(raw_args: str) -> str | None`, and its exceptions propagate to the chat surface.
A command's reply lands in the chat transcript, which may go to a cloud model. The pane is a
desktop contribution that a Python command cannot open (PC-3: the desktop half owns the UI).

## Goals / Non-Goals

Goals: a command that starts denial work from the chat and never puts PHI in the transcript.

Non-Goals: opening the pane from Python (no API for it); listing every open case (case IDs per
profile would need a new listing route for little gain over the pane's own list).

## Decisions

1. **Behavior (SPECS.md open question).** `/denial` answers a fixed guide (pane first, never paste
   documents, then `/denial <case ID>`, then ask about codes and payers); `/denial <case ID>`
   answers that case's summary. Rejected: opening the pane (no Hermes API from the Python half);
   listing open cases (a new route and an unbounded list in the transcript, while the pane
   already lists them).
2. **One path to case data: the guarded tool handler.** The command calls the same guarded
   `claimcoach_case_summary` handler the agent calls (US-9.2: de-identified by construction,
   redacted, audited), then renders text only from a `CaseSummaryResult` that still validates, or
   a known envelope's fixed message. A summary that no longer validates after redaction is shown
   as the `redaction_failed` message, never as raw JSON.
3. **No echo, no raise.** An argument that is not a case ID gets the guide, without quoting it;
   any exception becomes the `internal_error` message and is logged by type only.

## Risks / Trade-offs

- [A biller types a name after `/denial`] → it matches no case ID pattern or no case, and the
  reply is the guide or `case_not_found`; the name is never repeated.
