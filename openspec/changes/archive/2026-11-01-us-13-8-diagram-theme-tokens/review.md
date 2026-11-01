# Review: US-13.8

Change: us-13-8-diagram-theme-tokens
Reviewer: independent `story-reviewer` agent (read-only, given the change name and the changed files, not the implementer's reasoning), 2026-11-01
Verdict: not ready at review; pass after fixes (both themes checked in the browser pane; GitHub not seen)

The reviewer rendered the diagrams through `<img>` in headless Chrome, light and dark, and compared
each with a copy that removes text strokes.

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| critical | Container classes sat on both the `<g>` and its `<rect>`, so every text inherited the group's stroke: chip labels about 1.1–2:1 in light, type tags 3.79:1 in dark | Every container rule names its element (`rect.node`, `rect.chip`, `rect.tag`, …) and `text { stroke: none }`; the check resolves each text's computed stroke through the cascade and refuses any; `test_us_13_8_what_is_painted_is_measured` (group-stroke-inherited) |
| high | The contrast test hard-coded each text's background token and read only the text class's fill | `computed()` resolves the cascade, inheritance, and opacity; the background is the computed fill of the rect the text sits in, else the frame's wash, else the page; fixtures for a chip filled like its text and faded text fail |
| medium | The loop frame's wash was never modeled, and `contrast()` dropped a background's alpha | The wash is blended over the page in sRGB-encoded space and texts and marks inside it are measured against it; `opaque()` refuses a translucent background; `test_us_13_8_wash_and_lines_are_measured` |
| medium | "lines and arrows clear 3:1" was narrowed in the requirement and checked on a fixed list; `--ring` lines were 2.59:1 in light | Lifelines, zones, and the frame use `--chart-2` (4.73:1 light, 4.18:1 dark); every non-decorative stroke or fill rule is checked on the page and the wash; the Then names the lines, and box hairlines are recorded as decorative in SPECS.md for the PO |
| medium | The literal-color guard missed element selectors, `.dark` rules, named colors, and oklch | `color_problems` checks `fill`, `stroke`, `color`, `stop-color`, `flood-color`, and `lighting-color` in every rule outside the token blocks (only `var(--x)` or `none`) and refuses color attributes; `test_us_13_8_literal_colors_are_refused` |
| medium | Task 2.1 ticked without evidence | Evidence recorded (`junit.xml`, `test-report.md`) before archiving |
| medium | "For now use dark" vs. light values on light pages; design.md said the query follows the browser's preference | Recorded as a default for the PO in SPECS.md; design.md says Chrome resolves an `<img>` SVG's query from the embedding page's color scheme |
| low | "Older renderers show defaults" understated the failure | Non-goal stated: renderers without oklch or custom properties draw black boxes or refuse the file |
| low | The contrast math was not pinned | `test_us_13_8_contrast_math` pins luminance 0.17188 (#737373) and 4.73:1 on white |
| low | An extra `@media (prefers-color-scheme: dark)` would pass | `test_us_13_8_light_handled` requires exactly one `@media`, the light query |
| low | theme.css had an added header comment | Removed; the file is the theme as given |
| low (US-13.6 scope) | The guard ran over the pane lifeline | Moved to x = 108; the lifeline test covers the guard |

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
