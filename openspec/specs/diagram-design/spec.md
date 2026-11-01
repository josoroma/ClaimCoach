# diagram-design Specification

## Purpose
Defines the diagram-design rules ClaimCoach's diagrams follow.

## Requirements

### Requirement: The background is transparent
No diagram SHALL paint its whole canvas: no filled shape SHALL cover the viewBox, no style SHALL
set a `background`, and the light-page rules SHALL set only tokens.

#### Scenario: The background is transparent
- **WHEN** every diagram under docs/assets is parsed
- **THEN** no shape paints the whole canvas

### Requirement: Connectors are orthogonal on a 4px grid
Every connector SHALL use only absolute `M`, `H`, `V`, and `A` commands, run only horizontally or
vertically, and turn only through a quarter-arc elbow of radius 6 to 8 that sweeps the way the
path turns; every point of a connector and every box's position and size SHALL be a multiple of 4.

#### Scenario: Connectors are orthogonal on a 4px grid
- **WHEN** every diagram's connectors and boxes are read
- **THEN** every connector runs only horizontally or vertically, with rounded elbows
- **AND** every box's position and size is a multiple of 4

### Requirement: Nodes and labels follow the primitives
Node boxes SHALL be hairlines (1px, 1.2px for the accent) with a corner radius of at most 8 and no
filter; arrow labels SHALL be uppercase chips of at most 14 characters, except a sequence
diagram's messages, which are mono labels that, like its guard, sit over no other lifeline; the
title and description SHALL come first with IDs carrying the diagram's name.

#### Scenario: Nodes and labels follow the primitives
- **WHEN** every diagram's nodes and labels are read
- **THEN** node boxes are 1px hairlines (1.2px for the accent) with a corner radius of at most 8 and no shadow or filter
- **AND** arrow labels are uppercase chips of at most 14 characters
- **AND** the title and description IDs carry the diagram's name

### Requirement: Each diagram stays within its complexity budget
A diagram SHALL have at most 9 nodes, 12 connectors, 2 accent elements, and 2 callout lines; a
sequence diagram at most 5 lifelines, 12 messages, and 1 fragment.

#### Scenario: Each diagram stays within its complexity budget
- **WHEN** every diagram's parts are counted
- **THEN** it has at most 9 nodes, 12 connectors, and 2 accent elements
- **AND** the sequence diagram has at most 5 lifelines, 12 messages, and 1 fragment
