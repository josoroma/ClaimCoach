# Runbook: appeal drafting and export

Covers US-7.1 (draft a diagnosed case's appeal letter from the payer's rule cards and a letter
template, using Ternary-Bonsai-2-27B, the `drafting` role), US-7.2 (save edited text as the draft;
export the stored draft as PDF or DOCX), and US-7.3 (ClaimCoach has no send or submit capability).
Billers get this in the ClaimCoach pane: **Draft appeal** once the case is diagnosed, the draft
under "Draft for human review" in an editor, **Save draft**, then **Export PDF** or **Export DOCX**,
which opens the save dialog so the biller picks the folder. These commands are for operators
checking the worker by hand. Every command talks to the worker on `127.0.0.1` only (BR-1, BR-2);
the draft is stored encrypted with the case (BR-6) and purged with it (BR-7). Nothing here, or
anywhere in ClaimCoach, sends a letter: the biller sends the exported file through the practice's
normal channels (BR-4).

These commands print case content (the letter) to your terminal. Do not paste their output into
tickets, chats, or the agent transcript.

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- The case is diagnosed and its fields have not changed since: `make case-show CASE=<id>` shows a
  `diagnosis` with `"diagnosis_stale": false` (see [case-diagnosis](case-diagnosis.md)).
- `Ternary-Bonsai-2-27B-MTPLX-Optimized-Speed` is under `MODELS_HOME` and the `mtplx` venv exists
  (`make models-check` shows `drafting ... present  venv ok`; otherwise
  `make models-download ROLE=drafting CONFIRM=yes`). The 27B model is large: the memory guard
  unloads any other model of 14B or more before it starts (BR-12).
- The `drafting` command in `<hermes root>/plugin-data/claimcoach/models.yaml` ends with
  `"--reasoning", "off"` (copies made before US-7.1 lack it: see [upgrade](upgrade.md)).
  Without it the model's hidden reasoning uses up the reply, and drafts end `drafting_failed`.
- The global corpus holds a letter template: `appeal-<denial reason>` (underscores as hyphens,
  for example `appeal-prior-authorization`) or `appeal`, or the one you name with `TEMPLATE=`
  (`make corpus-list` shows `letter_template` items). For example:

  ```yaml
  items:
    - kind: letter_template
      template_id: appeal
      title: General appeal letter
      body: |
        [Practice letterhead]
        Re: Appeal of claim [Claim number], denied [Denial date]
        State the service, the denial reason codes, why the denial is wrong, and the enclosures.
      source: Practice letter library 2026
      verified_on: 2026-09-15
  ```

- Optional but expected: the payer has rule cards (see [case-diagnosis](case-diagnosis.md)); a
  case whose payer has none is still drafted, and the draft names no rule cards.

## Steps

1. Draft the letter; progress events print until the job ends (`done` or `failed`):

   ```bash
   make case-draft CASE=case_0123456789abcdef
   ```

   Name a template instead of the default choice:

   ```bash
   make case-draft CASE=case_0123456789abcdef TEMPLATE=appeal
   ```

2. Show the draft (a case access, audited `case_opened`):

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

3. Save edited text as the draft (the whole letter, from a local text file):

   ```bash
   make case-edit CASE=case_0123456789abcdef FILE=letter.txt
   ```

4. Export the stored draft and copy it out before it is removed:

   ```bash
   make case-export CASE=case_0123456789abcdef FORMAT=pdf TO=$HOME/Desktop
   ```

   ```bash
   make case-export CASE=case_0123456789abcdef FORMAT=docx TO=$HOME/Desktop
   ```

5. Run the offline tests, then the real-model drafting test (skips without the weights):

   ```bash
   make test-story STORY=US-7.1
   ```

   ```bash
   make test-story STORY=US-7.2
   ```

   ```bash
   make test-story STORY=US-7.3
   ```

   ```bash
   make test-models
   ```

## Verification

- Step 1 prints `drafting      0%` and ends with `done 100%`. A `failed` line names its code and
  `make` reports an error (exit status 2): `model_unavailable` (the model or the `mtplx` venv is missing or not
  healthy), `model_busy` (memory guard queue), `drafting_failed` (the model's answer held no
  letter; the previous draft is kept), `case_closed`, or `processing_timeout`.
- Before a job starts, drafting is refused with `not_diagnosed` (no diagnosis, or the fields
  changed since it ran: diagnose again), `no_letter_template` (no matching template: import one),
  or `case_not_found`. A case runs one job at a time: while it is being diagnosed, step 1 follows
  that job and exits 1; run it again once it ends.
- Step 2 shows `draft` with `"label": "draft for human review"`, the letter `text` (bracketed
  placeholders such as `[Patient name]` and `[Member ID]` stand for what the case does not hold),
  the `template_id` and `rule_cards` it was drafted from, and `"draft_stale": false`. After a
  confirmed field or a new diagnosis, `"draft_stale": true` until the case is drafted again.
  Drafting again replaces the draft, edits included.
- Step 3 shows the draft with the file's text and an `edited_at` time; it is refused with
  `not_drafted` (draft first), `model_busy` (a draft job is running on the case), `case_closed`,
  or `invalid_request` (empty text or more than 20,000 characters). Edits saved while a draft job
  runs are kept: the job ends `failed` with `draft_edited` and stores nothing.
- Step 4 prints `format`, `path`, `filename`, `size_bytes`, and `expires_at` (15 minutes after the
  export), then `copied to …`; a target file that already exists is refused before
  anything is exported (`… exists; choose another TO`), never overwritten. The file is under
  `<profile home>/plugin-data/claimcoach/exports/`, mode 0600 in a 0700 folder. The PDF opens in
  Preview with "Draft for human review" at the top of every page; the DOCX opens in Word or Pages
  with "Draft for human review" as its first line. Both hold the stored draft's text.
- `make corpus-audit CASE=<id>` shows `case_drafted`, `draft_edited`, and `draft_exported`
  entries with IDs and times only. No log line or event carries the letter.
- There is no command, route, or pane control that sends, submits, faxes, or e-mails the letter:
  `test_us_7_3_no_transmitting_route` pins every route and `test_us_7_3_no_send_contribution`
  checks every pane control.

## Rollback

- A draft is a starting point for the biller, never sent anywhere. A wrong one is replaced by
  running step 1 again (after correcting the fields and diagnosing again), or corrected with
  step 3; a failed run leaves the previous draft in place.
- A wrong template or rule card is fixed in the global corpus: correct it and re-import it under
  the same ID ([corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)),
  then run step 1 again.
- Exports remove themselves 15 minutes after they are written, and all of them go when the worker
  stops (`make worker-stop`, or quitting Hermes). To remove them sooner:

  ```bash
  rm -f "$HOME/.hermes/plugin-data/claimcoach/exports/"appeal-draft-*
  ```

  A copy the biller saved elsewhere is theirs to keep or delete.
- A draft is purged with its case: close the case and purge it on request with the privacy
  officer's approval ([phi-purge](phi-purge.md)): `make corpus-purge PROFILE=<p> CASE=<id> CONFIRM=yes`.
- The first worker start of this version rebuilds each user store's `case_items` table once so it
  accepts drafts; the rebuild is one transaction. Earlier versions open a migrated store and
  ignore drafts ([upgrade](upgrade.md)).
- If a letter appeared anywhere but the pane, this terminal, or the file the biller saved, follow
  [phi-incident](phi-incident.md).
