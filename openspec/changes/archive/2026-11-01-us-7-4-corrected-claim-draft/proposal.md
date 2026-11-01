# Proposal: US-7.4 Corrected Claim Draft

## Why

Some denials are not argued but fixed: a wrong modifier, a member ID the payer cannot match, a
claim returned as unprocessable. For those, the biller corrects the claim and resubmits it
instead of appealing (PRD §1: ClaimCoach "drafts the appeal letter or corrected claim"). US-7.4
was NEEDS CLARIFICATION on two product questions; the PM approved the defaults recorded in
SPECS.md on 2026-11-01: a corrected-claim draft is a typed list of changes for the biller to make,
not a claim form or an 837, and a fixed table, not the model, says whether a denial needs a
corrected claim or an appeal.

## What Changes

- `recommended_remedy(diagnosis, extraction, cards)`: a pure function that recommends a
  corrected claim, an appeal, either, or none (verify first), from the denial reason, the case's
  CARC/RARC codes, and the payer's `corrected_claims` rule card. `Case.remedy` shows it whenever
  the diagnosis is current; `Diagnosis` is unchanged.
- `CorrectedClaimDraft`: the label "draft for human review", the original claim ID, the claim
  frequency code as an instruction (1, 7, or 8, chosen by fixed rules), and one or more
  `ClaimCorrection`s (a line or the claim, a field from a closed enum, the current value only
  from the extraction, the codes behind it, and what to check or change, with why).
- A `correct` case job (`Corrector`): the lines, fields, current values, codes, and frequency
  code are filled deterministically; the `drafting` model writes only each change's action and
  why, as JSON, and the parser refuses a reply that names a code the documents do not hold.
  Stored as the `correction` case item; `Case.correction_stale` by the same extraction-digest
  and diagnosis-time check as the appeal draft.
- Routes `POST /cases/{case_id}/correction` (start the job) and
  `POST /cases/{case_id}/correction/export` (PDF or DOCX, `corrected-claim-draft-<case>.<ext>`),
  in the worker and through `plugin_api.py`; `WorkerClient.start_correction`,
  `export_correction`; error codes `correction_failed` and `not_corrected`.
- Corpus: a `corrected_claims` rule-card topic with `remedies` (per denial reason) and
  `frequency_code`; the per-case rule-card lists hold six cards.
- Pane: the recommended fix under the diagnosis, a Draft corrected claim button beside Draft
  appeal, the labeled list of changes, and its Export PDF / Export DOCX. No submit control.
- `make case-correct` and `make case-correction-export`; the appeal-drafting runbook covers
  corrected claims; the US-7.3 route pins and loopback walk cover the new routes.

## Capabilities

### New Capabilities

- `corrected-claim-draft`: the remedy recommendation, the corrected-claim draft and its job,
  staleness, export, and the no-send guarantee for it.

### Modified Capabilities

- None by delta. The `corrected_claims` rule-card topic and the new routes are specified as
  requirements of `corrected-claim-draft`; `appeal-draft`, `draft-export`, and `no-send-submit`
  keep their requirements.

## Impact

- New: `plugin/claimcoach/corrections/` (`types.py`, `remedy.py`, `draft.py`).
- Changed: `cases/diagnosis.py` (`Remedy`; six rule cards), `cases/models.py`,
  `cases/service.py`, `cases/extraction.py` (`JobKind`), `cases/errors.py`,
  `corpus/types.py` (item kind, audit actions), `corpus/bundle.py`, `agent/types.py` (topic),
  `letters/types.py`, `letters/export.py`, `pipeline/jobs.py`, `worker/app.py`,
  `worker/case_routes.py`, `api/models.py`, `api/client.py`, `api/routes.py`,
  `plugin/desktop/plugin.js`, Makefile, `docs/runbooks/appeal-drafting.md`,
  `docs/runbooks/corpus-import-reindex-backup-restore.md`.
- Store: `case_items` gains the `correction` kind; the existing CHECK migration rebuilds older
  tables. No new dependency.
