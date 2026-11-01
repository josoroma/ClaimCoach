# Design: US-8.3 manager-approved fine-tune export

## Context

Each outcome row (US-8.1) carries a de-identified snapshot (US-8.2): the payer as its rule cards
name it, the denial reason, and the codes. The classification model (US-6.1) reads `case_facts`:
the payer's printed name, the amounts, and per line the procedure code, adjustments, and remark
codes; never the claim number or a date. The retention purge removes a case's content 90 days
after it closes, so a pair built from the case at export time would usually find nothing. Hermes
has no manager role.

## Goals / Non-Goals

Goals: an explicit export, approved by a named manager each time, of the pairs a future fine-tune
of the classifier needs, holding no PHI, written to a file on this Mac.

Non-Goals: the fine-tune itself; scheduling or sending the export anywhere; exporting profiles
that do not share their outcomes.

## Decisions

1. **Records are built from the de-identified snapshot, never from case text (SPECS.md open
   question: record fields).** When the outcome is recorded, the snapshot also takes `ClaimFacts`
   and the appeal likelihood, but only from a diagnosis of the case's current fields. `ClaimFacts`
   is what the classifier read with every dollar amount dropped: each billed/paid pair becomes a
   payment status (`none`, `partial`, `full`), adjustments keep their group and reason codes. A
   record is `{format, payer, facts, codes, denial_reason, appeal_likelihood, outcome}`: the input
   the classifier saw, its label, and how the case ended. Every value is an enum or a
   pattern-checked code, or a global rule-card payer name, so the record is de-identified by
   construction, can sit unsealed in the outcomes table, and survives the purge. A snapshot over
   64 KiB (a claim of hundreds of lines) is stored without its facts: it still counts in the
   summary and is not exported. Rejected: keeping the amounts (review finding: they would sit
   unsealed beside the case ID, and US-8.2 left dollars out of the summary for the same reason);
   sealing them in a second column (the export would need every profile's key, for a signal the
   payment status keeps). Rejected:
   redacting the denial letter's text with the US-3.1 redactor (the scoping default first
   proposed). Redaction recall is below 100% by nature (NFR-4), a name or address the model misses
   would be exported, the source text is purged after 90 days, and the classifier never reads that
   text anyway. As a last guard, each serialized record runs through the US-3.1 regex validators
   and is withheld if one matches (`withheld`, expected 0).
2. **Format (SPECS.md open question): JSON Lines, one record per line, versioned per record.**
   `format: "claimcoach-fine-tune-1"`; a later layout gets a new name, so mixed files stay
   readable. Outcomes without a label or facts (no current diagnosis, recorded before this
   version, or too large) are left out and counted (`unlabeled`). Every outcome is read, whatever
   its date, so one stamped "later" than a clock that was set back is not lost. Only profiles whose `share_outcome_stats` is on
   are read (US-8.2's reader: read-only, no key, outcomes table only). Rejected: CSV (nested lines
   and adjustments); one JSON array (not streamable by fine-tune tools).
3. **Approval (SPECS.md open question): typed, per export, named, and logged.** The request is
   `{"approval": {"manager": "<name>", "approved": true}}`, strict (`approved` must be the boolean
   `true`; the name is 1 to 80 printable characters, so no line or paragraph separator can split
   a log entry). Without it, or with `approved: false`, the export is refused with
   `export_not_approved` (403) before any profile is read or any file written. Every approved
   export appends `{filename, records, profiles, approved_by, approved_at}` to `approvals.jsonl`.
   The log is opened before the export is written (`O_APPEND | O_NOFOLLOW | O_NONBLOCK`; it must be
   a regular file of this user, and is made 0600), and if its line cannot be written the export is
   deleted, so no export exists unlogged. The dashboard asks for the name and an "I approve" tick,
   untick after each export, so every export is approved anew; `make outcomes-export` counts only a
   `CONFIRM=yes` typed on its command line, not one left in the shell's environment.
   Rejected: a stored "exports allowed" setting (it would make exports routine, against PRD §9);
   per-profile audit entries (the audit log is per case and needs every profile's key).
4. **Where the file goes: the app-wide `fine-tune` folder, kept.** `<hermes root>/plugin-data/
   claimcoach/fine-tune/fine-tune-<UTC time>-<random>.jsonl`, written owner-only through a
   temporary name (`O_EXCL | O_NOFOLLOW`) and renamed, so a failure leaves nothing and no export
   replaces another; a symbolic link in the folder's place is refused. Unlike a draft export
   (US-7.2), it holds no PHI, so it is not swept; the manager moves or deletes it. Rejected: returning the records in the response body (the dashboard has no
   API to save it; a file on this Mac is what the PRD asks for).

## Risks / Trade-offs

- [A value mis-read into a code field (a ZIP code read as a five-digit CPT code) and confirmed by
  the biller] → the regex guard cannot tell them apart; the value carries no date, name, or
  claim number with it, and the export is a deliberate, logged act of the practice's manager on
  the practice's own Mac.
- [A manager name typed by anyone at this Mac] → Hermes has no roles; the approval is an explicit,
  logged attestation, not authentication.
