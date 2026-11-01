# Proposal: US-13.6 Diagram Text Stays Inside Its Container

## Why

In the dark theme, the stakeholder diagram's "rules · codes · templates" ran past the Global corpus
shape (user feedback, 2026-11-01). Nothing measured text against its container, so any later label
could overflow the same way (SPECS.md US-13.6).

## What Changes

- Every node, label chip, and type tag is a `<g class="node|chip|tag">` group whose first `<rect>`
  is the container of the group's texts.
- `tests/svg_layout.py` measures each text: diagram-design's budget (0.60em per character for sans,
  0.62em for mono, 0.50em for serif) or PyMuPDF's Helvetica, Courier, or Times metrics (+20% for
  proportional fonts, which covers DejaVu on Linux), whichever is wider, plus letter-spacing after
  every glyph.
- `tests/test_us_13_6_text_fit.py`: node text inside its box with 8px padding, chip and tag text
  inside its rect, free text inside the viewBox and off every node; overflows are reported by name.
- The overflowing label is fixed: the stakeholder nodes are 200px wide (US-13.7 redraws them).

## Capabilities

### New Capabilities
- `diagram-text-fit`: text measurement and the fit rules for every diagram.

### Modified Capabilities
- None.

## Impact

- Tests and diagrams only. A diagram edit that lets text overflow now fails `make check`.
