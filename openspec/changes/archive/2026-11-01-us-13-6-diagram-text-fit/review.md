# Review: US-13.6

Change: us-13-6-diagram-text-fit
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: pass after fixes (Windows fonts and Safari/WebKit not measured)

The reviewer rendered the three diagrams in headless Chromium and compared each text's real width
with the estimate under the macOS defaults, Helvetica/Arial/Liberation, an installed Geist, and
DejaVu. No current text overflowed; the findings were gaps in the check.

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| medium | The estimate was not conservative for DejaVu Sans Bold (+9.9%) or DejaVu Serif Italic (+8.6%), Linux's generic fallbacks; "Model download window" passed in a 200px node but rendered 2.3px past its border | Proportional metrics get a 20% margin (`_PROPORTIONAL_MARGIN = 1.2` in `tests/svg_layout.py`); design.md and the SPECS open question name the Linux fallback |
| medium | `inside()` applied padding only left and right, so "8px of padding on each side" was not checked | `inside(inner, outer, pad_x, pad_y)`; nodes use 8/8; `test_us_13_6_vertical_padding_is_checked` |
| medium | Task 2.1 was ticked with no `evidence/US-13.6/` | Evidence recorded (`junit.xml`, `test-report.md`) before archiving |
| low | Containers were matched on the exact class string, so `class="node accent"` escaped every check | `groups()` matches class tokens; `orphan_containers` fails on any node, chip, tag, or tab rect outside its group; `test_us_13_6_orphan_container_is_named` |
| low | `<tspan>`, `font-size`, `transform`, and similar were measured silently as plain text | `text_box` refuses children and any `style`, `font-size`, `font-weight`, `font-family`, `transform`, `dx`, or `textLength` attribute; `test_us_13_6_unmeasurable_text_is_refused` |
| low | Chips and tags were never checked against the canvas or the nodes; free text not against chips, tags, or the loop frame | Chip and top-level tag rects must be on the canvas and off every node; free text must miss nodes, chips, and tags, and text that starts in the frame must stay inside it; `test_us_13_6_free_text_off_canvas_is_named` |
| low | The overlap message did not say which node | Every problem names the node by its texts and the chip or tag by its label (`test_us_13_6_overflow_is_named` asserts the exact list) |
| info | Letter-spacing was counted for n−1 gaps; Chromium adds it after the last glyph too | The width counts n gaps |

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
