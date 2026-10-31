# Design: US-6.3 appeal deadline

## Context

US-6.1 and US-6.2 store a `Diagnosis` per case and find the payer's rule cards by whole-word
payer match at the start of the name (`corpus.lookup.payer_rule_cards`, one card per topic). Rule
cards carry free text plus structured fields stored as JSON metadata. The extraction (US-5.2) had
no date for the denial itself, only service dates. SPECS.md leaves three open questions: the final
rule-card format (now settled by US-4.3), what to show without a card or limit, and which date the
clock counts from.

## Goals / Non-Goals

Goals: a deadline equal to the denial date plus the payer card's appeal limit; a clear reason when
it cannot be computed; the denial date confirmable like any field.

Non-Goals: business-day or receipt-date clocks per payer; second-level appeal deadlines; reminders
and notifications; timely-filing limits for new claims (a different clock).

## Decisions

1. **The clock counts from the date of the payer's decision (resolves the third open question).**
   `denial_date` is the production date of the remittance or the date of the notice. From an 835
   it comes from the header of the transaction (`ST`) that holds the claim read: `DTM*405`
   (production date), else `GS04` of the enclosing group (the production date when `DTM*405` is
   absent, per the 835 TR3), else `BPR16` (the payment or EFT date, usually a few banking days
   later); only a valid `CCYYMMDD` counts, so a malformed segment falls through to the next
   source. A later transaction's dates never date the claim. On an EOB or letter the model reads
   the notice date. Payers that count from receipt give later deadlines, so counting from the
   production or notice date is never later than the payer's own. Rejected: `BPR16` before
   `GS04` (up to days late); the last `BPR` in the interchange (another transaction's date); a
   per-payer clock field (no card needs it yet).
2. **Calendar days.** `compute_deadline(denial_date, limit_days)` returns `denial_date +
   limit_days` days: a 180-day limit on a 2026-10-15 denial is due 2027-04-13. It is pure, typed,
   and refuses a limit below 1 (`ValueError`). Rejected: business days (no payer in scope uses
   them for appeals).
3. **The limit lives on the payer's `appeal_levels` card.** `RuleCard.appeal_limit_days` is a
   strict integer 1–3650 (YAML `yes` or `"180"` is refused), allowed only on that topic, stored as
   JSON metadata, and shown by `corpus list`. With two spellings of one payer, the most recently
   verified card is used (US-6.2). Rejected: parsing a number out of the card body (silently wrong
   when the body mentions several periods).
4. **No deadline is ever guessed (resolves the second open question).** `AppealDeadline.status` is
   `computed` (with `due`), or the first missing input in the order of who fixes it: `no_payer`
   (the biller confirms the payer), `no_rule_card` and `no_appeal_limit` (the manager adds a
   card), `no_denial_date` (the biller confirms the date), or `implausible_denial_date` (a date
   after today or before a service date: a misread year or a due date read as the notice date;
   the biller confirms it). Rejected: a default limit, or using any date the model read (a wrong
   deadline is worse than none).
5. **Computed whenever the case is read, never stored.** `CaseService` builds `Case.deadline` from
   the current extraction, the payer's current cards, and today's date on every read
   (`appeal_deadline` is pure; the card lookup reads the global store). A confirmed denial date
   or a re-imported card shows at once, a failed or missing model never hides it, and it cannot
   go stale. Rejected: storing it with the classification (the US-6.3 review found that a missing
   8B model hid the deadline, and a card change left a confident old date on screen).
6. **`denial_date` is an ordinary claim-level field; dates are `YYYY-MM-DD`.** It is placed after
   `paid_amount`, highlighted when unreadable, confirmed through `POST /fields`, and kept across a
   re-run like the other claim-level confirmations. Extractions stored before this change read it
   as unreadable. This field and the service dates accept only `YYYY-MM-DD` text (a number would
   otherwise be read as a Unix timestamp).

## Risks / Trade-offs

- [A wrong denial date gives a wrong deadline] → the date and the limit are shown next to the
  deadline, an implausible date is refused, and the field can be confirmed; an 835 date is exact.
- [A stale card may carry an old limit] → the card is named, and `corpus list` and the pane flag
  stale cards (US-6.2).
- [A deadline that has passed] → the pane says so in words, not only by date.
- [Older extractions now list one more field to confirm] → processing the case again reads it.
- [An earlier version cannot read new extractions] → the upgrade runbook says rolling back past
  US-6.3 needs the pre-upgrade backup.
