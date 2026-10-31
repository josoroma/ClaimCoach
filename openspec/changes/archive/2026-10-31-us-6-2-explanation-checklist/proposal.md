# Proposal: US-6.2 Plain-Language Explanation and Missing-Documentation Checklist

## Why

PRD §6 story 3: the biller sees a plain-language explanation of the denial, its likely root cause,
and a missing-documentation checklist; PRD §1: each case ends with a checklist the biller learns
from. PRD §8 names Qwen3-14B (the `explanation` role) for the explanation and checklist. The
checklist must come from the payer's rule card (PRD §9: rule cards hold required documents), never
from the model's imagination.

## What Changes

- `RuleCard` gains `required_documents` (a list, only on `required_docs` cards); it is stored with
  the card and validated at import. `item_document` stores non-text card fields as JSON.
- `corpus/lookup.py` gains `rule_card_of` (a stored document back to its `RuleCard`) and
  `payer_rule_cards` (the cards of the payer whose name matches the case's payer, by whole words,
  longest match wins).
- `cases/diagnosis.py`: typed `Explanation` (explanation, root cause), `ChecklistItem` (a required
  document, verbatim from the card, and why it matters here), `RuleCardRef` (the card used, with
  source, verified-on date, and the stale flag); `Diagnosis` carries them.
- `pipeline/explain.py`: the registered `explanation` template; `explain()` sends the case facts,
  the classification, the code notes, the payer's rule cards, and the numbered required-document
  list; the reply's checklist is read as item numbers, so every item is the card's own text.
- `Diagnoser` gains the `explaining` stage: it stores the classification first, then the
  explanation and checklist.
- `plugin.js`: shows the explanation, the root cause, the checklist with each item's reason, and
  the rule card it came from (flagged when stale), or says that no rule card is on file.
- The `case-diagnosis` runbook covers rule cards with required documents.

## Capabilities

### New Capabilities
- `case-explanation`: the plain-language explanation, root cause, and missing-documentation
  checklist of a diagnosed case.

### Modified Capabilities
- `corpus-import`: rule cards may list required documents.

## Impact

- The `explanation` role (Qwen3-14B, ≥ 14B) loads after classification; the memory guard keeps
  it from overlapping another ≥ 14B model (BR-12).
- Existing rule cards import and read unchanged; a `required_docs` card without a list gives an
  empty checklist until the manager adds one.
- US-7.1 drafting can attach the checklist's documents to the appeal.
