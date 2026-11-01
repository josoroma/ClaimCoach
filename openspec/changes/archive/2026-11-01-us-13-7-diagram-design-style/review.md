# Review: US-13.7

Change: us-13-7-diagram-design-style
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes (GitHub's rendering not seen; both themes checked in the browser pane)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | `JobStarted` was drawn from the worker straight to the pane, and `Case` skipped the gateway; the request test never read arrows | JobStarted returns worker → plugin_api → pane; `GET /cases/{case_id}` carries "proxied to the worker" and `Case` returns plugin_api → pane. `test_us_13_4_request_diagram_follows_request` pairs each label with the arrow 8px under it and asserts all twelve (label, from, to, kind) in order; probes moving JobStarted, extract, or the sealed write to the wrong lifeline fail it |
| medium | `path_problems` missed curves, relative commands, sharp corners, wrong sweeps, `rx != ry`, and r < 6 | Only absolute `M H V A`; a turn must be a quarter-arc with `rx == ry`, 6 ≤ r ≤ 8, and a sweep that matches the turn; `test_us_13_7_diagonals_and_off_grid_are_refused` holds ten refusals |
| medium | The transparency check saw only rect geometry and the zone rule | `background_problems` checks every painted shape's box against the viewBox, any CSS or root-style `background`, and non-token rules under the light query; `test_us_13_7_painted_backgrounds_are_refused` |
| medium | What the chat agent receives was only in `<desc>` | The agent's sublabel is "IDs · codes · payer names" and the crossing is labeled REDACTED ONLY; `test_us_13_4_stakeholder_diagram_shows_boundary` asserts both |
| medium | The per-launch token and the memory guard were no longer drawn | Notes "per-launch bearer token" and "first use · memory guard" under their messages, asserted by the request test. The 20 s poll bound is left to README-DEV.md ("long-polls"); AES-256 stays on the User corpus node |
| medium | Returns used the stakeholder legend's `nophi` dash, so PHI returns read as "no case content"; the request diagram had no legend | Returns use their own `return` class; the request diagram has a legend (call, return, event, the sealed write) |
| medium | Biller facts dropped from the user diagram were not moved to README-DEV.md as the proposal said | "For billers" now covers pasted 835, automatic diagnosis, the appeal-or-corrected-claim recommendation, the call's reference number and rep instructions, the retention purge, and the opt-in summary and approved fine-tune export |
| medium | Task 2.1 ticked without evidence; US-13.4's Gherkin and evidence still described the old background and dark rules | Evidence recorded for US-13.6 to 13.8; US-13.4's last two scenarios rewritten in SPECS.md and this change's `flow-diagrams` delta; US-13.4's evidence re-recorded against the rewritten tests |
| low | The loop framed the one-off model call and sealed write as if they repeated | The frame holds only the long-poll, its answer, and the progress event, guarded `[until the job ends]`; "The developer diagram follows one request" is replaced by "…one extraction"; the test asserts exactly those three messages lie within the frame's height |
| low | The user and stakeholder tests never read arrows | Arrows are read node to node: step n → n+1, the payer call → Add documents, the outcome → Manager dashboard (`nophi`); each step names only its roles' models; worker → User corpus solid, worker → Global corpus and Agent tools `nophi` |
| low | The guard sat over the pane lifeline and the lifeline test covered only messages | The guard starts at x = 108 and the lifeline test covers messages and the guard |
| low | The request diagram broke README's "every diagram" rules without a recorded exception | README-DEV.md states the sequence-type exceptions; design.md decisions 5 to 7 record them and the accent choice |
| low | Decision 3 said model downloads exchange no data with ClaimCoach | Rewritten: downloads cross inbound only after confirmation (BR-1) and stay a callout so the drawing keeps one outbound crossing |
| low | User legend, payer-call styling, "AFTER HOURS" arrow, and "shared corpus" wording misled | Legend "STEP n · YOU: your step"; the payer call is `node-optional` (dashed) tagged "V1.1 · AFTER HOURS" with a TRANSCRIPT arrow; the callout says "global corpus" |
| low | Chip gaps, worker attach points, uniform node treatment, and the callout budget were unpinned | Chips sit 8px from their segment, worker exits at 544/596/648, the chat agent and payer call use the optional treatment, and `test_us_13_7_within_budget` counts at most two callout lines |
| low | US-13.4 pinned three SVGs while US-13.6 to 13.8 globbed only `flow-*.svg` | US-13.6's `DIAGRAMS` (shared by 13.7 and 13.8) is every `docs/assets/*.svg` |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8551      0   1414      0   100%
=============== 1877 passed, 14 deselected in 238.26s (0:03:58) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-13.4
ok   US-13.6
ok   US-13.7
ok   US-13.8
================ 2 passed, 1889 deselected in 242.27s (0:04:02) ================
```
