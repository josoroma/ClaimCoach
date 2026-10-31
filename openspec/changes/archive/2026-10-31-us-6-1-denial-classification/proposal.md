# Proposal: US-6.1 Denial Classification and Appeal Likelihood

## Why

PRD §6 story 3: once a case is extracted, the biller sees why it was denied and whether an appeal
is worth filing (low/medium/high with reasons). PRD §8 names Qwen3-8B (the `classification` role)
for denial-reason classification and appeal likelihood as JSON. EPIC-6's other two stories
(explanation and checklist, deadline) build on the stored diagnosis this story introduces.

## What Changes

- `claimcoach/cases/diagnosis.py`: typed `DenialReason` (a closed set of 11 labels),
  `AppealLikelihood` (`low`, `medium`, `high`), and `Diagnosis` (reason, likelihood, one to five
  reasons, the codes it was based on, the digest of the extraction it read, and when it ran).
  Gateway-safe: Pydantic only.
- `claimcoach/pipeline/diagnose.py`: the registered `classification` prompt template, the case
  facts and code notes sent as data blocks, the reply parser, and `Diagnoser`, a job runner that
  reads the stored extraction, classifies it with the `classification` role, and stores the
  diagnosis as a sealed case item (audited `case_diagnosed`). It re-exports the three types.
- `claimcoach/corpus/lookup.py`: exact lookup of the global corpus's code entries for the case's
  CARC, RARC, and group codes; `CorpusStore.documents` gains a `kind` filter.
- Case items gain the kind `diagnosis`; an existing user store's `case_items` table is rebuilt
  once so its `CHECK` accepts every `CaseItemKind`.
- `JobRegistry` runs two job kinds (`extract`, `diagnose`), still one job per case; `JobStarted`
  says which kind it is. Worker `POST /cases/{id}/diagnose`; gateway `POST /cases/{id}/diagnose`
  relays its progress (`classifying`, then `done`) like extraction.
- `Case` carries the diagnosis and `diagnosis_stale` (the fields changed since it ran).
- New error codes `not_extracted` and `diagnosis_failed`.
- `plugin.js`: after a successful extraction the pane starts the diagnosis; it shows the denial
  reason and the appeal likelihood with its reasons, flags a stale diagnosis, and has a
  "Diagnose case" button.
- Makefile `case-diagnose`; runbook `case-diagnosis`.

## Capabilities

### New Capabilities
- `case-diagnosis`: denial classification, appeal likelihood with reasons, diagnosis jobs, and
  their display in the pane.

### Modified Capabilities
- None. `case-extraction`'s requirements hold unchanged; `JobStarted` gains a field with a
  default, and extraction jobs behave exactly as before.

## Impact

- The `classification` role (Qwen3-8B) loads during diagnosis; the memory guard sequences it
  with the other roles (BR-12).
- A user store opened by this version is migrated in place (one table rebuild inside a
  transaction); older versions keep working on it, since only the `CHECK` list grows.
- US-6.2 and US-6.3 extend `Diagnosis` and `Diagnoser`; US-7.1 drafting reads the diagnosis.
