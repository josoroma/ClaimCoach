# diagram-text-fit Specification

## Purpose
Defines how diagram text is measured and where it must fit.

## Requirements

### Requirement: Node text fits its box
Each text of a node SHALL fit inside the node's box with at least 8px of padding on each side,
measured as the wider of diagram-design's per-character budget and the font metrics.

#### Scenario: Node text fits its box
- **WHEN** each text inside a node of every diagram under docs/assets is measured
- **THEN** it fits inside the node's box with at least 8px of padding on each side

### Requirement: Labels and tags fit their chips
Each arrow label and type tag text SHALL fit inside its chip or tag rect.

#### Scenario: Labels and tags fit their chips
- **WHEN** the text of every arrow label and type tag is measured
- **THEN** it fits inside its chip

### Requirement: Free text stays on the canvas and off the nodes
Each text that belongs to no node, chip, or tag SHALL stay inside the viewBox and overlap no node.

#### Scenario: Free text stays on the canvas and off the nodes
- **WHEN** every text that belongs to no node, chip, or tag is measured
- **THEN** it stays inside the viewBox and overlaps no node

### Requirement: An overflow is named
The check SHALL fail on any overflow and name the text and its container.

#### Scenario: An overflow is named
- **WHEN** the check runs on a diagram whose text is wider than its box
- **THEN** it fails and names the text and its box
