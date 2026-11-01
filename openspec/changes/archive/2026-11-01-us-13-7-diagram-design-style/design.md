# Design: US-13.7 Diagrams in the diagram-design Style

## Context

diagram-design targets HTML pages with web fonts and a paper background. Ours are SVG images in
GitHub READMEs, where fonts cannot load and the page supplies the background.

## Goals / Non-Goals

- Goals: diagram-design's primitives, grid, connectors, labels, and budgets; a transparent canvas.
- Non-Goals: the HTML page shell, the Instrument Serif title header, animation.

## Decisions

1. **Labels are filled chips, not paper masks.** diagram-design masks labels with the paper color;
   on a transparent canvas a paper mask shows as a box anyway, so it is drawn as a deliberate chip
   in `--secondary`. Rejected: unmasked labels (unreadable over a connector).
2. **Type is one step larger than diagram-design's defaults.** README images scale to about 0.9;
   diagram-design scales type to the output ("a projected slide gets 16px node names"). Names 14px,
   sublabels 11px, labels and eyebrows 9px. Rejected: the 12/9/8px defaults (about 7px on GitHub).
3. **Over-budget content becomes callouts.** Model downloads cross the boundary inbound, only
   after you confirm one (BR-1), and payers receive nothing from ClaimCoach, so both are callouts:
   the drawing keeps its one outbound crossing, the redacted path to the chat agent. Rejected:
   splitting the stakeholder diagram (two images for one message) and a download arrow (it would
   read as a second path for case content).
4. **A box is a class, not a shape.** Databases are node boxes tagged SQLITE. Rejected: cylinders
   (a curved outline the text check cannot treat as a box).
5. **The request diagram is a sequence diagram.** It follows `type-sequence.md`, not the node
   primitives: lifeline heads carry a name and a mono sublabel but no type tag, messages are mono
   labels over their arrows (solid calls, dashed returns, a dashed arrow with an open head for the
   progress event), and its one fragment is a `LOOP` frame with a tab and a guard. Rejected: chips
   on messages (twelve chips over five lifelines crowd the lanes).
6. **The loop holds only what repeats.** The job's model call and sealed write happen once, so they
   are drawn once, after `JobStarted`; the frame holds the gateway's long-poll, its answer, and the
   event, guarded `[until the job ends]`. A sequence diagram cannot show that the polling runs while
   the job does, so README-DEV.md says it. Rejected: a `par` fragment (a second fragment, over the
   budget of one) and the old loop around the whole job (it said the model is called on every poll).
7. **One accent per diagram where the reader should look.** The Mac boundary and the redacted
   crossing in the stakeholder diagram, the human-review step in the user diagram, and the sealed
   write in the request diagram, the one message that stores case content.

## Risks / Trade-offs

- [diagram-design changes its rules] → the tests pin the rules adopted here, not the upstream repo.
