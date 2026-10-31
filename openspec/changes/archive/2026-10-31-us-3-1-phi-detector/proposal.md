# Proposal: US-3.1 PHI Span Detector with Regex Validators

## Why

Logs, events, and agent tool results must be redacted (BR-14, BR-3), and redactor recall is a
release gate (NFR-4, ≥ 98% on the synthetic set). Everything downstream in EPIC-3 needs one
redactor that finds PHI by category (SPECS.md US-3.1, PRD §8, §11).

## What Changes

- `claimcoach.redact.types`: `PhiCategory` (name, dob, mrn, member_id, ssn, address, phone, plus
  `other`), `PhiSpan`, `RedactionResult`, `RedactRequest`, `RedactResponse`.
- `claimcoach.redact.validators`: regex validators for SSN, MRN, DOB, phone, and member ID
  (DOB/MRN/member ID only after a label).
- `claimcoach.redact.detector`: `PhiDetector` asks Qwen3-8B (`phi_detection` role, through
  `ModelManager.use`) for a JSON list of verbatim PHI values per ≤ 6 000-character chunk, built
  with the US-3.6 prompt builder; values are located at every occurrence in the document.
- `claimcoach.redact.redactor`: `redact(text, spans)` (propagation, merge, placeholder
  replacement, second-pass regex check) and `Redactor` (model spans ∪ regex spans).
- `claimcoach.models.chat.chat_completion`: OpenAI-compatible call that accepts only a
  `BuiltPrompt`; loopback, `trust_env=False`.
- Worker `POST /redact` (mounted with the model routes); new error code `redaction_failed` (503).
- Synthetic fixture set `tests/fixtures/phi/phi_set.json` from a seeded generator.
- Makefile: `redact`, `phi-fixtures`, `test-story`, `test-models`, `doctor`, `start`, `stop`,
  `gateway-restart`, `plugin-install`; `evidence` records node JUnit for any story with node tests.
- Runbook `docs/runbooks/phi-redaction.md`.

## Capabilities

### New Capabilities
- `phi-redaction`: PHI span detection by category and redaction of a text.

### Modified Capabilities
- None.

## Impact

- `create_app(token, models)` now also mounts `/redact`; without a manager it is absent (404).
- `ErrorCode` gains `redaction_failed`.
- The fake model server accepts `--reply-file`.
