# Review: US-12.1

Change: us-12-1-redaction-recall-gate
Reviewer: independent `story-reviewer` agent (read-only, given the four EPIC-12 change names and the changed files, not the implementer's reasoning), 2026-10-31; findings that span the EPIC are recorded in each change they touch
Verdict: pass after fixes (the gate on the real PHI model stays UNVERIFIED: no worker runs on this Mac and its `models.yaml` does not validate)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | A unit counted as recalled when the whole value was gone, so `[ADDRESS], Port Ellery, OR 80210` or `(950) [PHONE]` scored as redacted | A unit is recalled only when neither the value nor any of its distinctive words (found in the original only inside PHI) remains (`leaked`). Design decision 2; `test_us_12_1_a_partly_redacted_value_is_a_miss`. The perfect fake model still passes (`test_us_12_1_gate_passes_at_target`) |
| low | The gate compared the value rounded to four places: 440/449 (0.97996) passed | `Score.meets` compares exact fractions; `value` is display only. Design decision 3; `test_us_12_1_recall_just_below_target_blocks_though_it_rounds_to_it` |
| low | Seeds were never checked to occur in their document, nor the seven categories to be present, so a `PHI_SET=` override could pass for free | `PhiEvalDocument` refuses a seed its text lacks; `PhiEvalSet` refuses a set missing a PRD category; both exit 2. `test_us_12_1_seeds_must_occur_and_cover_every_category` |
| low | A failed report write left `.redaction-recall.json.<pid>.tmp` in `evidence/` | `write_report` removes the temporary file on any failure and re-raises. Covered by `test_us_12_1_report_is_replaced_whole` (no stray files) |
| medium (EPIC) | `make evals` without `REVIEWS` printed "every eval gate passed" though NFR-2 was never measured | Recorded in US-12.2 |
| medium (EPIC) | An unexpected exception skipped the purge and printed its text | Recorded in US-12.2; `main` prints the exception type only and exits 2 |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8232      0   1362      0   100%
=============== 1683 passed, 14 deselected in 238.59s (0:03:58) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
ok   US-12.1
================ 2 passed, 1695 deselected in 241.92s (0:04:01) ================   (-m gate)
$ make evidence STORY=US-12.1
===================== 17 passed =====================
```

`make verify` ran once for the four EPIC-12 changes delivered together. The `models` tests skip
(no worker on this Mac); their rows are UNVERIFIED in `evidence/US-12.1/test-report.md`.
