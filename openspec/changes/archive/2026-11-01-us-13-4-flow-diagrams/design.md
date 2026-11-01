# Design: US-13.4 App Flow Diagrams for Stakeholders and Users

## Context

Diagrams render on GitHub, in editors, and in the Hermes plugin listing, in light and dark themes, through `<img>`, which runs no script and loads nothing else.

## Goals / Non-Goals

- Goals: a page that stays true to the code, checked by `make check`.
- Non-Goals: replacing the runbooks, which keep the operational detail.

## Decisions

1. Hand-written SVG with CSS classes, light colors by default and dark ones under `prefers-color-scheme`. Rejected: Mermaid (not rendered everywhere the READMEs are read, and no control over the boundary's look).
2. Each diagram paints its own background. Rejected: a transparent canvas, which leaves dark text on a dark page.
3. The boundary test reads text positions from the SVG. Rejected: only checking the labels exist, which would pass with the chat agent drawn inside the Mac.

## Risks / Trade-offs

- [A component is renamed] → the content tests name each component and fail until the diagram is updated.
