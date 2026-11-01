# Design: US-12.2 classification and draft-quality gates

## Context

The diagnosis job (US-6.1) classifies a case's extraction into one `DenialReason`; drafting
(US-7.1) writes the letter, and the biller edits it (US-7.2), which replaces the stored text. PRD
§11 lists labeled training/eval data as open. SPECS.md asks two questions; both are decided here,
and the story's status moves from NEEDS CLARIFICATION on these defaults.

## Goals / Non-Goals

Goals: an accuracy eval over a labeled set with an 85% gate; a draft-acceptance eval with a
written rubric and a 70% gate; both reports as evidence.

Non-Goals: collecting real partner data; a manager review UI; storing the model's original draft
next to the biller's edits (a case-store change for a later story).

## Decisions

1. **The labeled set is synthetic, labeled by construction, and pending human review (open
   question 1).** A seeded generator writes 20 cases, two per family other than `other`; each is
   denied under a reason code that `REASON_GUIDE` lists for its label (a test checks this), so the
   label is what a billing expert would assign. Payers, claims, and patients are invented. The
   set's `provenance` says it awaits a manager's review; a partner set with the same schema
   replaces it with no code change (`make eval-classification SET=…`). Rejected: waiting for
   partner data (blocks the gate indefinitely); Bonsai-generated cases (unreviewed model output
   would grade the model with itself).
2. **"Accepted with only minor edits" means the approved letter keeps at least 85% of the draft's
   words in order, and at least 85% of the approved letter is the draft's words (open question
   2).** `similarity` is the smaller of the two shares; the words kept in order are
   `difflib.SequenceMatcher`'s matching blocks over lower-cased word and punctuation tokens.
   Cutting the last quarter fails (0.75 kept), so does adding a third more text; rewording a
   salutation or a sentence passes. Rejected: `ratio()` alone (review finding: symmetric, so a
   draft with its last quarter cut scored 0.857 and passed). The manager supplies `{draft, final}`
   pairs (de-identified) in a review file; the eval needs no case access. Rejected: a manager
   checkbox per letter (subjective and not repeatable); character-level edit distance (penalizes
   reformatting).
3. **The whole pipeline is measured.** Each case runs from upload to diagnosis through the
   worker's REST API, so an extraction that misreads a code counts as a misclassification, as it
   would for the biller. Rejected: calling `classify` on gold extractions (overstates accuracy).
4. **Every eval case is purged when its flow ends** (`POST /corpus/purge` with `confirm: true`),
   finished, failed, failed unexpectedly (any other error becomes `worker_error`, never its text),
   or cancelled (Ctrl-C purges, then stops); a case that cannot be purged is named with its
   profile and the command to purge it. `--limit n` takes cases round-robin by document kind, as
   the latency benchmark does. Rejected: leaving cases to the retention schedule (90 days of eval cases in the list).

## Risks / Trade-offs

- [Synthetic letters are cleaner than real ones] → the provenance says so; the report names its
  dataset, so a release decision sees which set it rests on.
- [The rubric is lexical: a draft that keeps the words but loses a key fact still passes] → the
  manager curates the review file and rejects such drafts by replacing the argument; NFR-2 is a
  rate over many letters.
