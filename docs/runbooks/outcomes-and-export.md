# Runbook: case outcomes, the weekly summary, and the fine-tune export

Covers US-8.1 (record how a case ended: overturned, upheld, or written off, which closes the
case), US-8.2 (the manager's weekly denial-pattern summary, built only from profiles that opted
in), and US-8.3 (the manager-approved, de-identified fine-tune export). Billers mark outcomes in
the ClaimCoach pane: the **Outcome** section under the draft, with **Mark overturned**, **Mark
upheld**, and **Mark written off**, then **Close the case** to confirm. The manager reads the
summary and runs the export on the ClaimCoach dashboard (sidebar → ClaimCoach). These commands are
for operators checking the worker by hand. Every command talks to the worker on `127.0.0.1` only
(BR-1, BR-2).

An outcome is an enum, a date, and a de-identified snapshot (the payer as its global rule cards
name it, the denial reason, the codes, the appeal likelihood, and the procedure, adjustment, and
remark codes the classifier read, with each charge reduced to whether it was paid; never a name,
claim number, date of service, dollar amount, or document text) in the user store's `outcomes`
table. It is kept when the retention purge removes the case's content (BR-7).

`make case-outcome` prints the case (its fields and draft) to your terminal. Do not paste its
output into tickets, chats, or the agent transcript. The summary and the export hold no case
content.

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- For an outcome: the case exists in the profile (`make case-show CASE=<id>` answers it), no
  extraction, diagnosis, or draft job is running on it, and anything still to add to it has been
  added. Once an outcome is recorded the case is closed: it takes no new documents, field
  confirmations, jobs, or draft edits, and cannot be reopened. Exports of its draft still work.
- For the summary and the export: each profile that shares its outcomes has **Share this
  profile's de-identified case outcomes** on in Settings → Plugins → ClaimCoach, which stores
  `share_outcome_stats: true` in that profile's `config.yaml`:

  ```yaml
  plugins:
    entries:
      claimcoach:
        settings:
          share_outcome_stats: true
  ```

  Anything but an explicit `true` (a missing value, `"yes"`, `1`, or an unreadable file) is not
  shared.
- For the export: the manager approves this export, by name, now. An outcome becomes a pair only
  if the case was diagnosed (and not changed since) when its outcome was recorded.

## Steps

1. Record a case's outcome (`overturned`, `upheld`, or `written_off`):

   ```bash
   make case-outcome CASE=case_0123456789abcdef OUTCOME=overturned
   ```

2. Check the case and its audit entries:

   ```bash
   make case-show CASE=case_0123456789abcdef
   ```

   ```bash
   make corpus-audit CASE=case_0123456789abcdef
   ```

3. Read the weekly summary of the last completed week, or of a given ISO week:

   ```bash
   make outcomes-summary
   ```

   ```bash
   make outcomes-summary WEEK=2026-W44
   ```

4. Ask for the export without an approval (it must be refused), then with the manager's approval:

   ```bash
   make outcomes-export
   ```

   ```bash
   make outcomes-export MANAGER="Dana Lee" CONFIRM=yes
   ```

5. Read the approval log:

   ```bash
   cat "${HERMES_HOME:-$HOME/.hermes}/plugin-data/claimcoach/fine-tune/approvals.jsonl"
   ```

6. Run the offline tests:

   ```bash
   make test-story STORY=US-8.1
   ```

   ```bash
   make test-story STORY=US-8.2
   ```

   ```bash
   make test-story STORY=US-8.3
   ```

## Verification

- Step 1 shows the case with `"outcome": {"outcome": "overturned", "recorded_at": …}` and a
  `closed_at` time equal to the first outcome's `recorded_at`. Any other `OUTCOME` is refused by
  `make` before anything runs (exit status 2). The worker refuses with `model_busy` while a job
  runs on the case (record it when the job ends), `case_not_found`, or `invalid_request`.
  Recording an outcome again replaces it (a correction) and keeps the first `closed_at`, so the
  retention clock does not restart; a purged case takes a correction too.
- Step 2 shows `outcome_recorded` for every outcome and one `case_closed`, with IDs and times
  only. Adding a document to the case now answers `case_closed`.
- Step 3 shows `week`, `starts_at` and `ends_at` (Monday 00:00 to the next Monday 00:00 in this
  Mac's time zone, written in UTC), `timezone`, the `profiles` read, `not_shared` (how many
  profiles do not share; nothing of theirs was opened), `unreadable` (opted-in profiles whose
  database could not be read), `totals`, `by_category` (per payer and denial reason), and
  `by_code` (per payer and code). Each count has `overturned`, `upheld`, `written_off`, `total`,
  and `overturn_rate`. `timezone` is the Mac's IANA zone name (`America/Chicago`) when known.
  `payer: null` is a payer with no rule card; `denial_reason: null` is an
  outcome recorded without a current diagnosis (or before this version). A week that does not
  exist (`2027-W53`) is refused with `invalid_request`; a malformed one by `make` (exit status 2).
- The summary reads each profile's `corpus.sqlite3` read-only, without its Keychain key, under an
  SQLite authorizer that refuses any column of any table but `outcomes`
  (`test_us_8_2_reader_can_open_nothing_else`).
- Step 4's first command fails with `export_not_approved` and writes nothing (as does
  `CONFIRM=yes` without `MANAGER`, or `MANAGER` without `CONFIRM=yes` typed on that command line:
  a `CONFIRM` exported in your shell does not approve anything). The second prints `path`,
  `filename` (`fine-tune-<UTC time>-<random>.jsonl`), `records`, `unlabeled` (outcomes without a
  label or facts, left out), `withheld` (records a PHI validator matched, left out; expected 0),
  the `profiles` read, `approved_by`, and `approved_at`. The file is under
  `<hermes root>/plugin-data/claimcoach/fine-tune/`, mode 0600 in a 0700 folder; each line is one
  record with `format: "claimcoach-fine-tune-1"`, `payer`, `facts`, `codes`, `denial_reason`,
  `appeal_likelihood`, and `outcome`; `facts` holds codes and payment statuses (`none`,
  `partial`, `full`), no dollar amounts. If writing the approval log fails, the export file is
  removed: an export never exists without its log line.
- Step 5 shows one line per approved export: `filename`, `records`, `profiles`, `approved_by`,
  `approved_at`. Refused requests leave no line.
- No log line carries case content: the export logs its counts only.

## Rollback

- A wrong outcome is corrected by running step 1 again with the right one.
- A closed case cannot be reopened. If documents were still missing, start a new case for them
  (`make case-new`); the closed case's content is purged on its retention schedule
  ([phi-purge](phi-purge.md)), and its de-identified outcome stays.
- A profile stops sharing by turning the setting off (or removing `share_outcome_stats`); the next
  summary and export leave it out. Nothing was copied out of its store before, except the records
  of exports already approved.
- An export is a file the manager keeps or deletes; ClaimCoach never sends it anywhere. Delete one
  that should not exist:

  ```bash
  rm -f "${HERMES_HOME:-$HOME/.hermes}/plugin-data/claimcoach/fine-tune/"fine-tune-*.jsonl
  ```

  The approval log is the record of what was exported; keep it.
- The first worker start of this version adds a `features` column to each user store's
  `outcomes` table once; older outcomes keep no snapshot and count as unclassified. Earlier
  versions open a migrated store and ignore the column ([upgrade](upgrade.md)).
- If case content appears in a summary or an export, stop exporting and follow
  [phi-incident](phi-incident.md).
