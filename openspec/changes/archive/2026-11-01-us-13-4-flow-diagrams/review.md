# Review: US-13.4

Change: us-13-4-flow-diagrams
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes (GitHub's dark theme not seen; the dark rules were applied in the browser pane)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | Step 3 said the biller confirms every value before diagnosis; only unreadable fields are, and a fully read case diagnoses on its own | Step 3 and the description say so |
| medium | The request diagram drew the events poll after the store, as one call | Redrawn: a loop while the job runs holds the long poll, model start, call, sealed write, and the progress event |
| medium (tests) | The boundary check looked only for labels; a PHI arrow to the chat agent passed | Every arrow ending at the chat agent must be `leave` and start in the Agent tools box; labels must sit between them; duplicate labels refused |
| medium (tests) | The user check never tied numbers or models to steps; swapped titles, swapped models, or `Llama-70B` passed | Each step's number and chip must be in its card; the Extract, Diagnose, and Draft cards must name their roles' models; every model named must be a `models.yaml` folder |
| medium | The request diagram had no requirement or content test | Added to SPECS.md and the spec delta; `test_us_13_4_request_diagram_follows_request` reads routes, event, and ports from the code and checks order and the loop |
| medium | `url()` gaps in the shared SVG check | Fixed in `tests/svg_checks.py` (see US-13.1) |
| low-medium (tests) | Background and dark checks accepted an empty dark block, a late background, or no `.bg` fill | `bg` must be drawn first over the full viewBox, have light and dark fills, and every styled class must have a dark rule; `test_us_13_4_diagram_check_refuses_light_only` |
| low | Step numbers' contrast in dark mode; step 6 implied the corrected claim is editable; "sealed rows"/"per row"; two text-fit spots; payer names missing from the agent label; README check by substring; exactly-three-files pin | Dark `.n`/`.dot`/`.dotyou` colors; step 6 edits the letter; "per value"; card text shortened and the stray label removed; payer names added (SPECS too); images must appear under App flows outside comments; at least the three names |

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
