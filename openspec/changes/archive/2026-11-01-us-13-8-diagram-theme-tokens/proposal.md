# Proposal: US-13.8 Diagram Theme from the Design Tokens

## Why

The product owner gave the project's theme (light `:root` and `.dark` oklch tokens) and asked the
diagrams to use it, handling dark and light, dark for now (SPECS.md US-13.8).

## What Changes

- `docs/assets/theme.css`: the theme as given, the one source of the diagrams' colors.
- Each diagram copies the tokens it uses: `:root` light, `.dark` dark, and the light values again
  under `@media (prefers-color-scheme: light)` for a light page. The root has `class="dark"`, so
  dark is the default. Every fill and stroke is `var(--token)`; no literal color remains.
- Roles: `card`/`card-foreground` nodes, `muted-foreground` sublabels, arrows, and callouts,
  `secondary` chips, `border` hairlines, `ring` dashed zones and lifelines, `primary` the accent,
  `muted` the fragment wash.
- `tests/test_us_13_8_theme.py` checks the values against `theme.css` and WCAG contrast in both
  themes (text 4.5:1, arrows and the accent 3:1), blending translucent tokens in sRGB space.
- README-DEV.md (App flows) documents the conventions.

## Capabilities

### New Capabilities
- `diagram-theme`: diagram colors from the theme tokens, dark by default, light on a light page.

### Modified Capabilities
- None.

## Impact

- Diagrams, tests, and docs. The LOOP tab's text moved to the chip label color: in light mode the
  sublabel color on `--secondary` was 4.34:1.
