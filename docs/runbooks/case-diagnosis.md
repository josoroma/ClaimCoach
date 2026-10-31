# Runbook: case diagnosis

Covers US-6.1 (classify an extracted case's denial into a closed set of reasons and estimate the
appeal likelihood with reasons, using Qwen3-8B, the `classification` role), US-6.2 (explain the
denial in plain language with its likely root cause and a missing-documentation checklist drawn
from the payer's rule card, using Qwen3-14B, the `explanation` role), and US-6.3 (the appeal
deadline: the denial date plus the payer's appeal limit, or why it is unknown). Billers get this in
the ClaimCoach pane: a case whose fields were all read is diagnosed right after extraction, and
"Diagnose case" runs it again after fields are confirmed. These commands are for operators checking
the worker by hand. Every command talks to the worker on `127.0.0.1` only (BR-1, BR-2); the
diagnosis is stored encrypted with the case (BR-6) and purged with it (BR-7).

These commands print case content (the diagnosis and its reasons) to your terminal. Do not paste
their output into tickets, chats, or the agent transcript.

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- The case exists and was extracted: `make case-show CASE=<id>` shows an `extraction` (see
  [case-intake-extraction](case-intake-extraction.md)). Confirm unreadable fields first: a
  diagnosis reads the fields as they are when it runs.
- `Qwen3-8B-4bit` and `Qwen3-14B-4bit` are under `MODELS_HOME` and the `mlx-lm` venv exists
  (`make models-check` shows `classification ... present  venv ok` and the same for
  `explanation`; otherwise `make models-download ROLE=classification CONFIRM=yes` and
  `make models-download ROLE=explanation CONFIRM=yes`).
- For a deadline, the case has a denial date (`extraction.denial_date`: from the 835 transaction
  holding the claim, its `DTM*405`, else `GS04`, else `BPR16`; or the notice date the model read;
  confirm it with
  `make case-confirm CASE=<id> FIELD=denial_date VALUE=YYYY-MM-DD` when it is unreadable) and the
  payer has an `appeal_levels` card with `appeal_limit_days` (calendar days from the denial date).
- For a checklist, the payer has rule cards in the global corpus, one of them a `required_docs`
  card with `required_documents` (`make corpus-list` shows `rule_card <payer>/required_docs`). The
  card's payer must begin the case's payer name, by whole words (`ACME Health` matches
  `ACME HEALTH PLAN`; `Medicare` does not match `AETNA MEDICARE ADVANTAGE`; the longest matching
  card payer wins). `make corpus-list` shows how many documents each card lists. For example:

  ```yaml
  items:
    - kind: rule_card
      payer: ACME Health
      topic: appeal_levels
      title: ACME Health appeal levels
      body: First-level appeals within 180 days of the denial notice.
      appeal_limit_days: 180
      source: ACME Health provider manual 2026, section 9.0
      verified_on: 2026-09-15
    - kind: rule_card
      payer: ACME Health
      topic: required_docs
      title: ACME Health appeal documentation
      body: Appeals must include the documents below.
      required_documents:
        - Copy of the denial notice or remittance
        - Medical records for the date of service
      source: ACME Health provider manual 2026, section 9.1
      verified_on: 2026-09-15
  ```
- Optional: the global corpus holds code entries for the case's codes (`make corpus-list` shows
  `code` items such as `CARC/197`); they are sent to the model as notes. Import them with
  `make corpus-import FILE=<bundle>` ([corpus-import-reindex-backup-restore](corpus-import-reindex-backup-restore.md)).

## Steps

1. Diagnose the case; progress events print until the job ends (`done` or `failed`):

   ```bash
   make case-diagnose CASE=case_0123456789abcdef
   ```

2. Show the result (a case access, audited `case_opened`):

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

3. After confirming a field (`make case-confirm ...`), check that the diagnosis is flagged stale,
   then run step 1 again:

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

4. Run the offline tests, then the real-model classification test (skips without the weights):

   ```bash
   make test-story STORY=US-6.1
   ```

   ```bash
   make test-story STORY=US-6.2
   ```

   ```bash
   make test-story STORY=US-6.3
   ```

   ```bash
   make test-models
   ```

## Verification

- Step 1 prints `classifying   0%`, `explaining  50%`, and ends with `done 100%`. A `failed` line
  names its code and the command exits 1: `model_unavailable` (a model is missing or not
  healthy), `model_busy` (memory guard queue), `diagnosis_failed` (a model's answer did not
  validate), `case_closed`, or `processing_timeout`. A failure while `classifying` keeps the
  previous diagnosis; a failure while `explaining` keeps this run's classification without an
  explanation or checklist.
- A case that was never extracted is refused before a job starts with `not_extracted`; an unknown
  case with `case_not_found`. A case runs one job at a time: while it is being extracted, step 1
  prints `a extract job is already running on this case; following it, then run this target
  again`, follows that job, and exits 1; run step 1 again once it ends.
- Step 2 shows `diagnosis` with `denial_reason` (one of `eligibility`, `prior_authorization`,
  `medical_necessity`, `coding_error`, `missing_information`, `duplicate_claim`, `timely_filing`,
  `non_covered_service`, `bundling`, `coordination_of_benefits`, `other`), `appeal_likelihood`
  (`low`, `medium`, `high`), one to five `likelihood_reasons`, the `codes` it read, and
  `"diagnosis_stale": false`; then `explanation` (`explanation`, `root_cause`), `checklist` (each
  `document` exactly as the payer's `required_docs` card lists it, with a `why` when the model gave
  one), and `rule_cards` (each card used with `source`, `verified_on`, and `stale`). With no
  matching rule card, `checklist` and `rule_cards` are empty and the pane says no rule card is on
  file; when the model picks no listed document, every listed document is shown.
- `make case-show` shows the case's `deadline` as soon as the case is extracted, diagnosed or not,
  computed on every read from the current fields and cards: `"status": "computed"` with `due`
  equal to `denial_date` plus `limit_days` calendar days (a 180-day limit on 2026-10-15 is due
  2027-04-13) and the `rule_card` it came from; the pane says "Appeal by …" and flags a date that
  has passed. Otherwise `due` is `null` and `status` names the first missing input: `no_payer`
  (confirm the payer), `no_rule_card`, `no_appeal_limit` (no `appeal_levels` card with
  `appeal_limit_days`), `no_denial_date`, or `implausible_denial_date` (after today or before the
  date of service: confirm the date). A confirmed date or a re-imported card shows on the next
  `make case-show`, without diagnosing again. No default limit is ever used.
- Step 3 shows `"diagnosis_stale": true` until the case is diagnosed again.
- `make corpus-audit CASE=<id>` shows `case_diagnosed` entries (two per run: the classification,
  then the explanation), with IDs and times only. No log line or event carries the reason, the likelihood, or any case value.

## Rollback

- A diagnosis is advice for the biller, never sent anywhere. A wrong one is replaced by running
  step 1 again after correcting the fields; a failed run leaves the previous diagnosis in place.
- A wrong or missing checklist comes from the rule card: fix the card's `required_documents` and
  re-import it under the same payer spelling, which replaces it; then run step 1 again. There is
  no command to delete a card: to correct a payer's spelling, re-import the card under the new
  spelling with today's `verified_on`, since per topic the most recently verified card of a payer
  is used (`Aetna` and `AETNA` are one payer).
- A wrong deadline comes from the denial date or the card: confirm the right date
  (`make case-confirm ... FIELD=denial_date VALUE=YYYY-MM-DD`) or fix and re-import the card's
  `appeal_limit_days`; the next read shows the corrected deadline.
- A diagnosis is purged with its case: close the case and purge it on request with the privacy
  officer's approval ([phi-purge](phi-purge.md)): `make corpus-purge PROFILE=<p> CASE=<id> CONFIRM=yes`.
- The first worker start of this version rebuilds each user store's `case_items` table once so it
  accepts diagnoses; the rebuild is one transaction. To go back to an earlier version, restore the
  backup taken before the upgrade ([upgrade](upgrade.md)); earlier versions also open a migrated
  store, ignoring diagnoses.
- If a diagnosis or its reasons appeared anywhere but the pane or this terminal, follow
  [phi-incident](phi-incident.md).
