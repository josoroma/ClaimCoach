# Design: US-6.2 explanation and missing-documentation checklist

## Context

US-6.1 stores a `Diagnosis` per case (denial reason, appeal likelihood with reasons) from a job
that reads the extraction. Rule cards (US-4.3) are free-text items keyed `<payer>/<topic>` with
topics `timely_filing`, `appeal_levels`, `required_docs`, `submission`, `other`, each with a source
and a verified-on date; the corpus view flags cards older than 180 days. The `explanation` role is
Qwen3-14B on `mlx_lm.server`. Prompts come only from registered templates (US-3.6, BR-10).

## Goals / Non-Goals

Goals: a plain-language explanation and likely root cause per diagnosed case; a checklist of
missing documents drawn only from the payer's rule card; show which card it came from and whether
the card is stale.

Non-Goals: ticking checklist items off and tracking which documents were gathered (a later pane
story); drafting the appeal (US-7.1); retrieving the payer's letter text from the case's PDFs.

## Decisions

1. **Required documents are structured on the card.** `RuleCard.required_documents` is a list of
   up to 30 entries of 1–200 characters, allowed only on `required_docs` cards (any other topic with
   a list is refused at import, so a list never hides where nobody looks). It is stored in the
   document metadata as JSON (`item_document` now writes non-text fields as JSON and skips
   defaults, so existing cards' metadata is unchanged). Rejected: asking the model to read the
   required documents out of the card's body text, which cannot guarantee the checklist only
   holds the card's own items.
2. **The model chooses among numbered items; the card supplies the words.** The prompt lists the
   card's documents as `1. …`, `2. …`; the reply's checklist holds item numbers with a short
   reason. Numbers outside the list or repeated are dropped; the items keep the card's order and
   text. When the card has documents but the reply selects none that are valid, every document is
   listed (without a reason): a payer requirement is never hidden because the model said
   nothing. Rejected: free-text checklist items (invented requirements); always listing every
   document (less useful when a card covers several denial families).
3. **"Missing" means not in the case.** ClaimCoach's case holds only the denial documents, so
   every required document the appeal needs is missing until the biller gathers it; the
   checklist says what to gather. Tracking what was gathered is a later pane story.
4. **The payer's card is found by whole words at the start of the name, longest match.** Payer
   names are compared case-insensitively as words (punctuation is a separator, a leading `the` is
   ignored); a card's payer matches when its words begin the case's payer name (`Aetna` matches
   `AETNA LIFE INSURANCE CO`), and the card payer with the most words wins (`Aetna Better Health`
   over `Aetna`). A carded payer named inside another payer's name never matches (`Medicare` does
   not match `AETNA MEDICARE ADVANTAGE`, nor `Health Net` `AMBETTER FROM HEALTH NET`). Two
   spellings of one payer (`Aetna`, `AETNA`: different keys, the same words) are one payer: per
   topic the most recently verified card is kept, so a diagnosis names at most one card per topic
   (five); one bundle may not spell a payer two ways. An unreadable payer or no match means no
   rule card: the checklist is empty, and the pane asks to confirm the payer or to add a card.
   Rejected: words anywhere in the name (the review found nested names picking another payer's
   card); embedding similarity (can pick another payer's card, the worst error here); exact
   equality (EOBs spell payers in full); refusing a second spelling at import (it would block
   correcting a card's payer name).
5. **Every card of the matched payer is context; the `required_docs` card is the checklist.**
   All the payer's cards (bodies capped at 4000 characters each) go to the model as data, so the
   explanation can cite appeal levels or submission rules; the `RuleCardRef` list on the diagnosis
   names each card used with its source, verified-on date, and stale flag (PRD §11).
6. **Two stores, two saves.** The job stores the classification as soon as it is ready
   (`classifying` 0 → `explaining` 0.5), then the explanation and checklist (`done` 1.0). If the
   14B model is missing or its reply does not validate (`diagnosis_failed`), the classification
   from this run stays visible. Rejected: one save at the end (a missing 14B model would hide a
   classification the 8B model already made).
7. **The reply is validated like the classification.** `explanation` (1–2000 characters) and
   `root_cause` (1–500) are required, non-blank strings; checklist entries are read one at a time
   (a malformed entry is dropped, never the whole reply), each reason at most 300 characters.

## Risks / Trade-offs

- [A wrong payer match would apply another payer's rules] → whole words at the start of the
  name only, the card used is named in the pane with its source, and an unmatched payer gets no
  checklist. Remaining risk: a short card payer that begins a different payer's name (`Blue
  Cross` for `BLUE CROSS AND BLUE SHIELD OF TEXAS`); managers name cards as specifically as the
  payer prints itself, and the pane shows which card was used.
- [A stale card may list outdated requirements] → the pane flags it, judged again for today (the
  stored flag is as of the diagnosis), as the corpus view does; `corpus list` shows each card's
  number of required documents.
- [The 14B model may write a misleading explanation] → it is shown as guidance next to the
  codes and the card it came from; drafts stay "for human review" (BR-4).
- [Card bodies enlarge the prompt] → each is capped at 4000 characters and a payer has at most
  five topics.
