# Proposal: US-9.1 Code and Payer-Rule Tools

## Why

PRD §6 story 6: a biller asks the Hermes agent "what usually fixes CO-197 for this payer?" and
gets an answer from the global corpus without the agent seeing the case. US-1.1 registered
`claimcoach_explain_code` and `claimcoach_payer_rules` as placeholders answering
`not_implemented`; US-4.3 imports the code entries and rule cards they need.

## What Changes

- `agent/types.py`: typed `ExplainCodeParams`/`ExplainCodeResult` (`CodeExplanation` entries) and
  `PayerRulesParams`/`PayerRulesResult` (`PayerRuleCard`s). The tool JSON schemas stay generated
  from the parameter models; reference text is capped at 4000 characters per entry (`truncated`).
- `agent/answers.py` (worker only): `code_keys` reads `CO-197` as `GROUP/CO` + `CARC/197`, `197`
  as `CARC/197`, `N286` as `RARC/N286`; `explain_code` and `payer_rules` answer from the global
  scope with the stale flag (US-4.3) and US-6.2's payer matching.
- Worker `POST /agent/explain-code` and `POST /agent/rule-cards` (the tool parameters are the
  body); `WorkerClient.explain_code`, `WorkerClient.payer_rules`; new codes `code_not_found` and
  `payer_not_found` (404).
- `agent/tools.py`: each `ToolSpec` carries its result model and its worker call; the handler
  validates, calls the worker through `guard.run_blocking` (generalised from the guard), and
  answers the result JSON or a fixed envelope. Registration still wraps it in
  `redact_tool_result` (US-3.2).
- `make agent-tools`, `make agent-call`; the `agent-tools` runbook.

## Capabilities

### New Capabilities
- `agent-reference-tools`: the code and payer-rule tools the Hermes agent calls.

### Modified Capabilities
- None (`tool-result-guard`'s requirements are unchanged; its handlers now return real results).

## Impact

- The US-1.1 placeholder test now expects `worker_unavailable` when no worker runs.
- Two worker routes, pinned in `test_us_7_3_no_transmitting_route` after a BR-4 review: they read
  the global scope only.
