# Design: US-13.8 Diagram Theme from the Design Tokens

## Context

An SVG shown through `<img>` cannot see the page's `.dark` class; it only sees
`prefers-color-scheme`. GitHub serves README images to the reader's browser, which supports oklch.

## Goals / Non-Goals

- Goals: the theme's exact values; dark by default; readable on light and dark pages.
- Non-Goals: the logo (US-13.1's brand mark keeps its colors); tokens the diagrams do not use;
  renderers without oklch or CSS custom properties (Safari before 15.4, ImageMagick, some IDE
  previews), which draw black boxes or refuse the file.

## Decisions

1. **Mirror the theme's own structure.** `:root` holds light, `.dark` holds dark, and the root
   element carries `class="dark"`; a light page re-applies the light values with
   `@media (prefers-color-scheme: light) { :root.dark { ... } }`. Removing the class makes it light
   everywhere. Rejected: dark-only (a transparent canvas would put near-white text on a light page).
2. **Accent is `--primary`.** The theme is neutral; `--primary` is the highest-contrast mark in both
   modes. Rejected: `--sidebar-primary` (blue in dark only, under 3:1 on the dark background).
3. **Free text is measured against `--background`.** The canvas is transparent, so the page is the
   background; the theme's background stands for it.
4. **Selectors name the element, and text never takes a stroke.** A node group and its rect share
   a class name (`node`), so `rect.node` styles the box and `text { stroke: none }` keeps a group's
   stroke from outlining its letters. The check resolves the cascade (specificity, inheritance,
   opacity) for every element instead of reading one rule per class.
5. **Contrast is computed as the browser paints.** oklch values are converted to sRGB, translucent
   tokens (the dark `--border`) and the loop frame's wash are blended in sRGB-encoded space, and
   WCAG's relative luminance is taken of the result: text 4.5:1, essential marks 3:1, against the
   surface each one sits on (its node, chip, tab, the frame's wash, or the page).

## Risks / Trade-offs

- [A reader's browser without oklch] → every current browser supports it (see Non-Goals).
- [The PO asked for dark "for now"] → dark is the default, but a page that prefers light gets the
  light values; the review saw Chrome resolve an `<img>` SVG's media query from the embedding
  page's color scheme, so GitHub's light theme shows the light diagrams. Dark-only was rejected
  (Decision 1) and the choice is recorded in SPECS.md for the PO.
- [Lines the theme leaves faint] → box hairlines are decorative (`--border` is about 1.3:1 in
  light); every line that carries meaning uses `--chart-2` or `--primary` and is checked at 3:1.
