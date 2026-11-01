# Design: US-13.6 Diagram Text Stays Inside Its Container

## Context

The diagrams are SVGs shown as images: Geist cannot load, so the browser falls back to SF Pro,
Segoe UI, Helvetica, Arial, or on Linux DejaVu Sans (sans), SF Mono, Menlo, or DejaVu Sans Mono
(mono), and Georgia, Times, or DejaVu Serif (serif). The gate cannot run a browser.

## Goals / Non-Goals

- Goals: no text runs past its container on any of those fallbacks; an overflow names the text.
- Non-Goals: pixel-exact layout of each font.

## Decisions

1. **Measure with the wider of diagram-design's budget and real font metrics.** The budget is
   diagram-design's own rule ("don't estimate widths by eye"); PyMuPDF's base-14 metrics catch wide
   strings (bold capitals) the budget underestimates, with 20% for proportional fallbacks: the
   review measured DejaVu Sans Bold and DejaVu Serif Italic up to 19% wider than Helvetica-Bold
   and Times-Italic in Chromium. Rejected: a headless browser (not available offline in the gate); a fixed
   characters-per-box limit (ignores weight and size).
2. **Containers are explicit groups.** A text belongs to the `<g>` it is in, not to whatever rect
   happens to surround it. Rejected: geometric guessing (the old cylinder was a `<path>`).

## Risks / Trade-offs

- [A fallback font wider than the margin; Windows' Segoe UI was not measured] → 8px padding inside nodes leaves more room; the margin is one constant in `tests/svg_layout.py`.
- [A text the estimate cannot see: tspans, size or transform attributes] → refused, so the check fails closed.
