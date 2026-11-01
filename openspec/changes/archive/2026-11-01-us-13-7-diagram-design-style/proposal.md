# Proposal: US-13.7 Diagrams in the diagram-design Style

## Why

The product owner asked for the diagrams to follow github.com/cathrynlavery/diagram-design on a
transparent background, with labels (SPECS.md US-13.7). The earlier diagrams painted their own
background, used diagonal arrows and hand-picked colors, and exceeded diagram-design's budgets.

## What Changes

- The stakeholder, user, and request diagrams are redrawn with diagram-design's primitives: node
  boxes (1px hairline, rx 6, type tag, name, mono sublabel), orthogonal connectors with r=8
  elbows on a 4px grid, uppercase label chips, a legend strip, callouts, and for the sequence
  diagram lifelines, a LOOP fragment with a guard, and solid calls, dashed returns, and an open
  async head. At most 9 nodes, 12 connectors, and 2 accent elements each.
- The stakeholder diagram keeps 9 nodes: model downloads and payers become callouts in the outside
  band. The user diagram's step cards keep the step tag, name, and model; the descriptions move to
  the README text.
- No background: the canvas is transparent; zones have no fill.
- IDs carry the diagram's name (`flow-user-title`, `flow-user-head`, ...).
- `tests/test_us_13_7_diagram_design.py`; `tests/test_us_13_4_flow_diagrams.py` reads the new
  markup (node groups by name).

## Capabilities

### New Capabilities
- `diagram-design`: the diagram-design rules every diagram follows.

### Modified Capabilities
- `flow-diagrams`: the self-contained requirement no longer asks for an own background.

## Impact

- Diagrams and tests only. A scratch generator wrote the SVGs; the committed SVGs are the source.
