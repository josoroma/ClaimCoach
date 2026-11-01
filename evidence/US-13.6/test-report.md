# Test Report: US-13.6 Diagram Text Stays Inside Its Container

Change: us-13-6-diagram-text-fit
Story: US-13.6
Verdict: pass
Coverage: 4/4 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; PyMuPDF base-14 font metrics; Chromium in the Claude desktop browser pane for the visual check

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Node text fits its box: Then it fits inside the node's box with at least 8px of padding on each side" | PASS | `test_us_13_6_node_text_fits[flow-*.svg]`: every name, sublabel, and type tag inside each `<g class="node">` is inside its box with 8px on all four sides. Widths are the wider of diagram-design's per-character budget and PyMuPDF's Helvetica/Courier/Times metrics with a 20% margin on the proportional ones (DejaVu on Linux, the reviewer's widest fallback, is 9.9% over Helvetica-Bold). `test_us_13_6_vertical_padding_is_checked` shows a name 2.75px from the bottom edge fails; `test_us_13_6_anchors_are_measured` covers start, middle, and end anchors |
| 2 | "Labels and tags fit their chips: Then it fits inside its chip" | PASS | `test_us_13_6_labels_fit_chips[flow-*.svg]`: every chip label and tag text is inside its rect with 3px of side padding, and every chip or top-level tag (the `LOOP` tab) is on the canvas and covers no node |
| 3 | "Free text stays on the canvas and off the nodes: Then it stays inside the viewBox and overlaps no node" | PASS | `test_us_13_6_free_text_on_canvas[flow-*.svg]`: every eyebrow, callout, legend, message, note, and guard is inside the viewBox and overlaps no node, chip, or tag; text that starts in the loop frame stays inside it |
| 4 | "An overflow is named: Then it fails and names the text and its box" | PASS | `test_us_13_6_overflow_is_named` asserts the exact problems for a Global corpus node 160px wide: "'rules · codes · templates' runs past its node (Global corpus / rules · codes · templates)", a tag past its node, a label past its chip, a chip over a node, and a callout over a node. `test_us_13_6_free_text_off_canvas_is_named`, `test_us_13_6_unmeasurable_text_is_refused` (a `<tspan>`, a `font-size`, or a `transform` fails closed), and `test_us_13_6_orphan_container_is_named` cover the rest |

## Evidence Commands

```bash
make evidence STORY=US-13.6
make check   # ruff, ruff format, biome, mypy --strict, tsc --checkJs, offline pytest + node --test
```

```text
===================== 21 passed, 1870 deselected in 1.41s ======================
TOTAL    8551      0   1414      0   100%
=============== 1877 passed, 14 deselected in 238.26s (0:03:58) ================
ℹ tests 191
ℹ pass 191
ℹ fail 0
```

Artifacts: `evidence/US-13.6/junit.xml`

## Failures

None.

## Notes

- The reported bug is fixed: the stakeholder nodes are 200px wide, and "rules · codes · templates" sits inside Global corpus in both themes (seen in the browser pane, dark and light).
- The independent review rendered the diagrams in headless Chromium with the macOS, Helvetica/Arial/Liberation, Geist, and DejaVu fallbacks. Windows fonts (Segoe UI, Consolas) and Safari/WebKit were not measured.
- Review fixes (see review.md): a 20% margin for proportional fallbacks, vertical padding, class-token matching, fail-closed text, chip/tag/frame overlaps, and named boxes in every message.
