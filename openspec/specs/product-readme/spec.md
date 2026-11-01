# product-readme Specification

## Purpose
Defines README.md as ClaimCoach's product page and the rules every README follows.

## Requirements

### Requirement: README.md is the product page
README.md SHALL show the shared logo, the problem, who ClaimCoach is for, what it does, the v1 targets, the privacy promise, and the user flow diagram, with no install or engineering steps, and SHALL link README-DEV.md.

#### Scenario: README.md is the product page
- **WHEN** a reader opens README.md
- **THEN** it shows the shared logo, the problem, who it is for, what it does, the v1 targets, and the privacy promise
- **AND** it shows the user flow diagram
- **AND** it has no install or engineering steps, and links README-DEV.md for them

### Requirement: The product claims come from the PRD
README.md's v1 targets table SHALL equal PRD §4's rows word for word, and its status SHALL say what has not been verified against the real models or a live Hermes Desktop.

#### Scenario: The product claims come from the PRD
- **WHEN** README.md states the v1 targets
- **THEN** each target equals the PRD's

### Requirement: Every README uses the shared logo
Every README*.md at the repository root SHALL show `plugin/assets/claimcoach-logo.svg` as its only logo, and every relative link and anchor in it SHALL resolve inside the repository, with exact case.

#### Scenario: Every README uses the shared logo
- **WHEN** a README*.md at the repository root shows a logo
- **THEN** it references plugin/assets/claimcoach-logo.svg
- **AND** every relative link in it resolves to a file in the repository
