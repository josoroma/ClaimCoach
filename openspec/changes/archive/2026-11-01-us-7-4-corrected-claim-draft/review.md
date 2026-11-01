# Review: US-7.4

Change: us-7-4-corrected-claim-draft
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01; independent `story-tester` agent (operator run over fake models), 2026-11-01
Verdict: pass after fixes (drafting with the real Ternary-Bonsai-2-27B stays UNVERIFIED: no worker runs on this Mac and its `models.yaml` does not validate)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The reply parser let modifiers and dotless ICD-10 codes through: `modifier-59`, `a 59 modifier`, `the XS modifier`, `99213-25`, `mod 59`, `modifier "59"`, `E119`, `M545`, `J449` | `_invents` refuses a modifier next to "modifier"/"mod" in either order with any separator, after a procedure code, or a letter modifier alone, and ICD-10 codes with or without the dot; `X12` and `P2P` are words. Each phrase is a case of `test_us_7_4_reply_that_proposes_a_code_is_refused`; `test_us_7_4_a_reply_may_repeat_what_the_documents_hold` keeps prose and the case's own codes |
| high | `PayerRulesResult.cards` still held five cards, so `claimcoach_payer_rules` failed for a payer with a sixth, `corrected_claims`, card (a US-9.1 regression) | `max_length=MAX_RULE_CARDS`; `test_us_7_4_a_payer_with_six_cards_still_answers_the_agent` |
| low | The pane's stale test did not follow the Gherkin trigger: changed fields make the diagnosis stale too | `changed fields: re-diagnose first, then Draft corrected claim again is offered` (node): the button waits for the diagnosis, then offers the redraft |
| low | Changes beyond 40 (a claim-level code on a long claim) were dropped silently | The draft lists 40 and records `omitted`; the pane and the export say so. `test_us_7_4_changes_beyond_forty_are_counted`, `changes the draft does not list are counted, so every line is checked` (node) |
| low | `X12`, `P2P` read as ICD-10 codes and refused a good reply | `NOT_CODES`; covered by `test_us_7_4_a_reply_may_repeat_what_the_documents_hold` |
| low | A fallback change with no codes read listed none | The pane says "Codes: none read." as the export does; asserted in `test_us_7_4_pane_value_missing_from_documents_is_never_invented` and `test_us_7_4_export_text_says_what_is_missing` |
| observation (tester) | A stale corrected-claim draft exported without saying so | The export opens with "OUT OF DATE: the case changed after this draft was made"; asserted in `test_us_7_4_draft_goes_stale_after_re_extraction` |
| observation (tester) | "Payer rule cards used" listed the payer's appeal cards | Renamed "Payer rule cards on file when drafted": the cards are those the model was given |

Also checked and found sound by the reviewer: the routing table, code splits, and rule-card override; the frequency-code rules; the strict types (label literal, current value only on a line's procedure code or service date); the `Corrector` refusals before the model loads; remedy-on-read and the shared stale check; the item-kind migration and purge; the routes, client, relayed `not_corrected`; the export label, filename, sweep, and modes; the US-7.3 pins and walks; the Make targets and runbooks.

While re-verifying, `test_us_12_4_one_sample_always_follows_the_flow` (EPIC-12) failed once under the full suite's load: it required exactly one `lsof` sample after the export, but a regular sample may also land during the purge that follows it. It now requires the last sample to follow the flow and at least one after the export.

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8682      0   1442      0   100%
=============== 1766 passed, 14 deselected in 242.75s (0:04:02) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-7.4
================ 2 passed, 1778 deselected in 249.78s (0:04:09) ================   (-m gate)
$ make evidence STORY=US-7.4
===================== 77 passed, 1703 deselected in 4.55s ======================
```

The `models` tests skip without weights; US-7.4 adds none (its drafting call is the US-7.1 model's,
whose real-model test is US-7.1's).
