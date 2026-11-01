# agent-reference-tools Specification

## Purpose
Defines the Hermes agent tools that answer from the ClaimCoach global corpus: what a denial code
means and what a payer's rule cards require.

## Requirements

### Requirement: explain_code answers from the global corpus
`claimcoach_explain_code` SHALL answer a code with the global corpus entries it names (the group
code's, then the reason or remark code's) as a JSON string validating against `ExplainCodeResult`,
each entry with its source, verified-on date, and stale flag. A code with no entry SHALL be
answered with the `code_not_found` envelope.

#### Scenario: explain_code answers from the global corpus
- **WHEN** the global corpus contains an entry for CO-197 and the agent calls claimcoach_explain_code with code CO-197
- **THEN** the tool returns a JSON string validating against the typed ExplainCodeResult with the corpus entry

#### Scenario: An unknown code is not guessed
- **WHEN** the agent calls claimcoach_explain_code with a code the corpus has no entry for
- **THEN** the tool returns the code_not_found envelope

### Requirement: payer_rules returns the payer's rule card
`claimcoach_payer_rules` SHALL answer a payer name with the matched payer's global rule cards, one
per topic, as a JSON string validating against `PayerRulesResult`, without echoing the asked name.
A payer no card matches SHALL be answered with the `payer_not_found` envelope.

#### Scenario: payer_rules returns the payer's rule card
- **WHEN** the global corpus contains a rule card for a payer and the agent calls claimcoach_payer_rules with that payer name
- **THEN** the tool returns a JSON string validating against the typed PayerRulesResult with that card

### Requirement: Tool handlers never raise
Every tool handler SHALL return a JSON string: the typed result, or a fixed error envelope
(`invalid_request`, a worker refusal's code, or `worker_unavailable`), and SHALL never echo its
arguments.

#### Scenario: No worker running
- **WHEN** the worker is not running and the agent calls a tool
- **THEN** the tool returns the worker_unavailable envelope
