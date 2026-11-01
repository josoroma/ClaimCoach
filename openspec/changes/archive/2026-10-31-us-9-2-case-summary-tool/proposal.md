# Proposal: US-9.2 Redacted Case Summary Tool

## Why

PRD §7 and §7.2: `claimcoach_case_summary` lets the Hermes agent discuss a case by ID without
seeing PHI. US-1.1 registered it as a placeholder; US-6.1 gives a case codes, a denial reason, and
an appeal likelihood worth summarizing.

## What Changes

- `agent/types.py`: `CaseSummaryParams` takes `case_id` only (`extra="forbid"`);
  `CaseSummaryResult` holds the case ID, `status` (`open`/`closed`), `stage` (`intake`,
  `extracted`, `diagnosed`, `drafted`), the outcome, the payer as the global rule cards name it,
  the codes, the denial reason, the appeal likelihood, whether the diagnosis is out of date, the
  deadline status (no dates), and counts of documents and fields to confirm.
- `agent/answers.py`: `case_summary` builds it in the worker from the stored extraction,
  diagnosis, draft, and outcome; no claim number, date, amount, printed payer name, or document
  text is read into it. Every summary is audited `case_summarized` (new `AuditAction`).
- Worker `POST /agent/case-summary?profile=…` (body `{case_id}`); `WorkerClient.case_summary`; the
  handler sends the active Hermes profile, so another profile's case is not found (BR-5).
- `make agent-call TOOL=claimcoach_case_summary ARGS='{"case_id": "…"}'`.

## Capabilities

### New Capabilities
- `agent-case-summary`: the redacted case summary the Hermes agent reads by case ID.

### Modified Capabilities
- None (`case-audit` gains an action value; its requirements are unchanged).

## Impact

- Audit logs show `case_summarized` entries when the agent reads a case.
