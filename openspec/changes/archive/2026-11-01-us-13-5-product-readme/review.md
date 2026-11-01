# Review: US-13.5

Change: us-13-5-product-readme
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | Status overstated what was verified: no feature has run against the real local models or a live Hermes Desktop | Status says exactly that; `test_us_13_5_readme_is_product_page` pins the sentence |
| medium | "The only outbound calls are model downloads and corpus imports" contradicted the diagram (the chat agent may be cloud) and corpus imports are local | Now: ClaimCoach's own outbound calls are confirmed model downloads; a cloud chat agent receives only case IDs, codes, payer names, and redacted summaries |
| medium | The corrected claim was described as an editable claim | Described as a list of corrections to make in the billing system, exportable |
| medium | Targets implied a labeled de-identified set and manager reviews exist | The table is PRD §4 verbatim, and the page names both inputs as still to be sourced (the gate runs on 20 synthetic cases until then) |
| medium (tests) | Cross-file anchors, paths outside the repository, case mismatches, titled and reference-style links, and fenced pseudo-headings were not checked | `broken_links` in `tests/doc_checks.py` covers each; `test_us_13_5_link_check_finds_broken_links` has a case for every one |
| medium (tests) | The target comparison checked only the leading number | The README table must equal PRD §4's rows word for word |
| low (tests) | The no-install check missed inline commands and indented code, and flagged prose | Refuses fences, indented code, and inline spans starting with a command word; prose is free |
| low | Logo detection saw only `<img>`; "Learns from outcomes"; the agent "without seeing the case"; the manager view without opt-in; SPECS sources; EPIC row status; UTF-8 read | `images()` finds Markdown and `<img>` images; wording fixed; Source adds §7.2, §8, §9; EPIC-13 row set on delivery; `encoding="utf-8"` |
| medium | Dependency order and untracked files | The five changes are delivered and archived together, and the helpers live in `tests/doc_checks.py` and `tests/svg_checks.py`; nothing is committed until the user asks |

## Re-verification

```text
$ make verify
All checks passed!
TOTAL    8682      0   1442      0   100%
=============== 1812 passed, 14 deselected in 244.06s (0:04:04) ================
ℹ pass 191
ℹ fail 0
ℹ   plugin.js | 100.00 |   100.00 |  100.00 |
ok   US-13.1
ok   US-13.2
ok   US-13.3
ok   US-13.4
ok   US-13.5
================ 2 passed, 1824 deselected in 248.32s (0:04:08) ================
```

The first `make verify` run failed once in its nested `make check` (the gate's self-test):
`test_us_2_2_group_members_are_stopped_with_the_leader` raised `PermissionError` from `os.killpg` in
`_group_alive` (`plugin/claimcoach/models/manager.py`, EPIC-2), which catches only
`ProcessLookupError`. It passed 5 of 5 runs alone and on the second `make verify`. This change does
not touch that code; it is reported to the user as a separate follow-up.
