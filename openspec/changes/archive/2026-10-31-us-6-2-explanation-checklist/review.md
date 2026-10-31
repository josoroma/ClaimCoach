# Review: US-6.2

Change: us-6-2-explanation-checklist
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, on a frozen snapshot of the change
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Two spellings of one payer (`Aetna`, `AETNA`) are separate cards; matching returned both, so six cards overflowed `Diagnosis.rule_cards` (max 5) and every diagnosis for that payer failed, and with fewer the stalest spelling's `required_docs` card could supply the checklist; the runbook's "fix its payer name, re-import" created exactly this | `payer_rule_cards` keeps one card per topic, the most recently verified (then the key), so at most five; one bundle may not spell a payer two ways; the runbook says to correct a spelling by re-importing with today's `verified_on`; `test_us_6_2_two_spellings_are_one_payer`, `test_us_6_2_two_spellings_in_one_bundle_refused` |
| medium | Whole-word matching anywhere in the name picked another payer's card for nested names (`Medicare` for `AETNA MEDICARE ADVANTAGE`, `Health Net` for `AMBETTER FROM HEALTH NET`) | A card's payer must begin the case's payer name (a leading "the" ignored), longest wins; design decision 4, its risk (the remaining short-prefix case), and a new spec requirement with scenarios; `test_us_6_2_payer_cards_match_by_whole_words` covers the nested names |
| low | The "nothing is stored" refusal test posted only the invalid card | The bundle now holds a valid card and the invalid one; the global scope stays empty (`test_us_6_2_list_on_another_topic_refused`) |
| low | No `models` test ran the 8B → 14B handoff through `ModelManager`; the 14B test passed even when every checklist entry was invalid (the fallback lists all) | `test_us_6_2_diagnosis_real_models` runs `Diagnoser.run` end to end under the memory guard; both real-model tests assert a model-given reason on the checklist |
| low | `corpus list` did not show a card's required documents | `CorpusViewItem.required_documents` (and US-6.3's `appeal_limit_days`); `corpus list` appends `(4 required documents)`; `test_us_6_2_corpus_list_shows_required_documents` |
| info | The bundle size cap ignored `required_documents` | Counted now; `test_us_6_2_required_documents_count_toward_the_size_cap` |
| info | Storing and reading card fields used different rules (runtime type vs a hardcoded name set) | One source: `bundle.STRUCTURED_CARD_FIELDS`, JSON on write and read |
| info | `RuleCardRef.stale` was frozen at diagnosis time | The pane judges staleness again for today (`staleOn`); `a card that became stale after the diagnosis is flagged today` |
| info | With an unreadable payer the pane told the biller to add rule cards | The pane asks to confirm the payer instead; `an unreadable payer asks the biller to confirm it, not the manager to add a card` |
| info | Tasks unchecked, evidence missing | Evidence recorded in `evidence/US-6.2/`; tasks checked before archive |

Also checked by the reviewer and found sound: Gherkin coverage on the API and the pane; `checklist_from` and `ExplanationReply`; `item_document`'s `exclude_defaults` keeping existing metadata unchanged; the `required_docs`-only rule; the two saves and the `explaining` stage; no model held across a save; the moves to `facts.py` and `replies.each_valid`; BR-1, BR-2, BR-5, BR-10, BR-11, BR-12, BR-14; ES-8.

## Re-verification

`make verify` → exit 0 on the fixed tree with all three EPIC-6 changes (2026-10-31): ruff, ruff
format, biome, mypy --strict ×2, tsc --checkJs; 1075 offline pytest tests passed at 100% line and
branch coverage of `plugin/`; 87 node tests at 100% line, branch, and function coverage of
`plugin.js`; evidence-check `ok` for every report through US-6.3 (OhMyOrch accepted each); 2 gate
self-tests passed. Evidence recorded by the independent `story-tester` after the fixes, including
an operator run of `make case-diagnose`, `case-show`, and `case-confirm` against a scratch worker
with fake models and synthetic data. The real-model tests skipped: the Qwen3-8B and Qwen3-14B
weights are not under `~/Models`, so the models' own answers are UNVERIFIED in the reports.
