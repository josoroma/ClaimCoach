# Test Report: US-13.7 Diagrams in the diagram-design Style

Change: us-13-7-diagram-design-style
Story: US-13.7
Verdict: pass
Coverage: 8/8 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Chromium in the Claude desktop browser pane for the visual check

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "The background is transparent: Then no shape paints the whole canvas" | PASS | `test_us_13_7_background_transparent[*.svg]`: no element whose computed fill is not `none` covers the viewBox, no CSS or root `style` sets a `background`, and the light-page `@media` rule sets only tokens. `test_us_13_7_painted_backgrounds_are_refused` shows a full-canvas path, `svg{background}`, a root `style="background"`, and a zone filled under the light query each fail |
| 2 | "Connectors are orthogonal on a 4px grid: Then every connector runs only horizontally or vertically, with rounded elbows" | PASS | `test_us_13_7_connectors_orthogonal_on_grid[*.svg]` runs `path_problems` on every arrow: only absolute `M H V A`, no diagonal or sharp corner, every turn a quarter-arc with `rx == ry` and 6 ≤ r ≤ 8 whose sweep matches the turn. `test_us_13_7_diagonals_and_off_grid_are_refused` refuses `L`, lowercase `l`, a `C` curve, a sharp corner, r = 12, r = 4, a non-quarter arc, and a backwards sweep |
| 3 | "Connectors are orthogonal on a 4px grid: And every box's position and size is a multiple of 4" | PASS | Same test: every node, zone, chip, tag, tab, and frame rect has x, y, width, and height on the 4px grid, and every connector point is on it |
| 4 | "Nodes and labels follow the primitives: Then node boxes are 1px hairlines (1.2px for the accent) with a corner radius of at most 8 and no shadow or filter" | PASS | `test_us_13_7_primitives_followed[*.svg]`: `rect.node` and `rect.node-accent` stroke at most 1.2 (1 and 1.2 in the files), every node `rx` ≤ 8, no `<filter>` and no `filter` property |
| 5 | "Nodes and labels follow the primitives: And arrow labels are uppercase chips of at most 14 characters" | PASS | Same test: every chip label is uppercase and ≤ 14 characters. The request diagram is a sequence diagram: its messages are mono labels, and `test_us_13_7_sequence_labels_clear_other_lifelines` checks each message and the guard sits over no other lifeline |
| 6 | "Nodes and labels follow the primitives: And the title and description IDs carry the diagram's name" | PASS | Same test: `role="img"`, `aria-labelledby="<stem>-title <stem>-desc"`, the title first, and every marker ID prefixed with the diagram's name |
| 7 | "Each diagram stays within its complexity budget: Then it has at most 9 nodes, 12 connectors, and 2 accent elements" | PASS | `test_us_13_7_within_budget[*.svg]`: stakeholder 9 nodes, 8 connectors, 2 accents; user 9 nodes, 8 connectors, 1 accent; request 5 nodes, 12 connectors, 1 accent; at most 2 callout lines each |
| 8 | "Each diagram stays within its complexity budget: And the sequence diagram has at most 5 lifelines, 12 messages, and 1 fragment" | PASS | Same test on `flow-request.svg`: 5 lifelines, 12 messages, 1 `LOOP` frame |

## Evidence Commands

```bash
make evidence STORY=US-13.7
make evidence STORY=US-13.4   # the request diagram's messages and loop, read from the redrawn SVGs
uv run python <scratchpad>/mut14/probe.py <scratchpad>/mut14   # the reviewer's US-13.4 mutations
make check
```

```text
===================== 24 passed, 1867 deselected in 1.40s ======================
====================== 4 passed, 1887 deselected in 1.42s ======================
caught jobstarted_skips_gateway - AssertionError: (assert)
caught extract_from_pane - AssertionError: (assert)
caught pane_writes_corpus - AssertionError: (assert)
caught model_call_in_loop - AssertionError: only the polling repeats
caught token_note_dropped - KeyError: 'per-launch bearer token'
caught user_arrow_reversed - AssertionError: no arrow from Add documents to Extract
caught drafting_on_extract - AssertionError: Extract names the models of its own roles only
caught user_corpus_dashed - AssertionError: case content stays on the Mac; only redacted results reach the chat agent
caught agent_label_dropped - AssertionError: what it may see
TOTAL    8551      0   1414      0   100%
=============== 1877 passed, 14 deselected in 238.26s (0:03:58) ================
```

Artifacts: `evidence/US-13.7/junit.xml`

## Failures

None.

## Notes

- All three diagrams were viewed in the browser pane on a dark and a light page: transparent canvas, orthogonal connectors with rounded elbows, every label inside its chip, and the request diagram's loop around the polling only.
- How GitHub renders them was not seen.
- The redraw changed what US-13.4 asserts about the request diagram. Its scenario "The developer diagram follows one request" is replaced by "The developer diagram follows one extraction" in this change's `flow-diagrams` delta and in SPECS.md.
- Review fixes (see review.md): JobStarted and Case return through the gateway; the token and memory guard are drawn; returns use their own `return` class, and a legend is added; the loop holds only the polling; the connector and background checks are stricter; the "For billers" paragraph is restored in README-DEV.md.
