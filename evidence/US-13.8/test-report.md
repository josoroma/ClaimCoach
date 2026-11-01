# Test Report: US-13.8 Diagram Theme from the Design Tokens

Change: us-13-8-diagram-theme-tokens
Story: US-13.8
Verdict: pass
Coverage: 5/5 acceptance criteria evaluated
Date: 2026-11-01
Tester: Claude Code (Opus 5.5), implementer run after the independent review fixes
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Chromium in the Claude desktop browser pane, with color-scheme emulation, for the visual check

## Acceptance Criteria Evaluated

Each Gherkin scenario's Then and And clauses are separate rows.

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "Colors come from the theme tokens: Then every fill and stroke is a theme token" | PASS | `test_us_13_8_colors_from_tokens[*.svg]`: outside the token blocks, every `fill`, `stroke`, `color`, `stop-color`, `flood-color`, and `lighting-color` is `var(--token)` or `none`, and no element carries a color attribute. `test_us_13_8_literal_colors_are_refused` shows `text{fill:white}`, `rect{stroke:oklch(0.5 0 0)}`, `.dark .rule{stroke:#fff}`, and a `fill="red"` attribute each fail |
| 2 | "Colors come from the theme tokens: And each token's light and dark values equal the theme's" | PASS | Same test: each SVG's `:root`, `.dark`, and light-override values for the tokens it uses equal `docs/assets/theme.css` |
| 3 | "Dark is the default: Then it uses the theme's dark values" | PASS | `test_us_13_8_dark_by_default[*.svg]`: the root has `class="dark"`, so `.dark` wins over `:root` without a light preference. Seen in the browser pane with dark emulation |
| 4 | "Light is handled: Then it uses the theme's light values" | PASS | `test_us_13_8_light_handled[*.svg]`: exactly one `@media` block, `(prefers-color-scheme: light)`, whose `:root.dark` rule sets the theme's light values. Seen in the browser pane with light emulation |
| 5 | "Text and marks stay readable in both themes: Then text clears 4.5:1, and connectors, arrowheads, lifelines, zones, and the loop frame clear 3:1" | PASS | `test_us_13_8_contrast_in_both_themes[*.svg]` resolves each text's computed fill, stroke (must be `none`), and opacity, and measures it against the fill of the rect it sits in (node, chip, tab), the loop frame's wash, or the page, in both themes. `test_us_13_8_what_is_painted_is_measured` shows an inherited group stroke, a chip filled like its text, and faded text each fail. `test_us_13_8_contrast_math` pins `oklch(0.556 0 0)` to luminance 0.17188 (#737373) and 4.73:1 on white. Marks: every non-decorative stroke and fill rule (arrows, heads, lifelines, zones, the frame, accents) clears 3:1 on the page and on the loop's wash in both themes. `test_us_13_8_wash_and_lines_are_measured` shows a heavy wash under the guard and a `--ring` lifeline (2.59:1 in light) fail |

## Evidence Commands

```bash
make evidence STORY=US-13.8
make check
```

```text
===================== 21 passed, 1870 deselected in 1.48s ======================
TOTAL    8551      0   1414      0   100%
=============== 1877 passed, 14 deselected in 238.26s (0:03:58) ================
```

Artifacts: `evidence/US-13.8/junit.xml`

## Failures

None.

## Notes

- Box hairlines (nodes, chips, tags, the loop's tab) and the legend rule are decorative and are not held to 3:1; in the light theme a node's `--border` hairline is about 1.3:1. SPECS.md records this as a default for the PO to confirm.
- "For now use dark": dark is the default, and a page that prefers light gets the light values, because a transparent dark drawing is unreadable on a white page. SPECS.md records this for the PO.
- Renderers without oklch or CSS custom properties (Safari before 15.4, ImageMagick, some IDE previews) are a non-goal.
- Review fixes (see review.md): text no longer inherits a group's stroke, contrast is measured against the real container fill and the loop's wash, the literal-color guard covers every color property, the contrast math is pinned, and the light query is the only `@media` block.
