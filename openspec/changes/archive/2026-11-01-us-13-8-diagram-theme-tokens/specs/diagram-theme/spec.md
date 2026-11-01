# Spec Delta

## Purpose

Defines where the diagrams' colors come from and how they switch between dark and light.

## ADDED Requirements

### Requirement: Colors come from the theme tokens
Every fill and stroke of a diagram SHALL be a theme token (`var(--token)`) or `none`, and each
token's light and dark values SHALL equal `docs/assets/theme.css`.

#### Scenario: Colors come from the theme tokens
- **WHEN** the colors of every diagram under docs/assets are read against docs/assets/theme.css
- **THEN** every fill and stroke is a theme token
- **AND** each token's light and dark values equal the theme's

### Requirement: Dark is the default
The diagram's root SHALL carry `class="dark"`, so the theme's dark values apply unless the page
prefers a light color scheme.

#### Scenario: Dark is the default
- **WHEN** a diagram renders without a light color-scheme preference
- **THEN** it uses the theme's dark values

### Requirement: Light is handled
Under `prefers-color-scheme: light`, the diagram SHALL apply the theme's light values.

#### Scenario: Light is handled
- **WHEN** a diagram renders on a page that prefers a light color scheme
- **THEN** it uses the theme's light values

### Requirement: Text and marks stay readable in both themes
In both themes, text SHALL clear 4.5:1 against what it sits on, and every connector, arrowhead,
lifeline, zone, frame edge, and accent SHALL clear 3:1 against the page and the loop's wash. Box
hairlines (nodes, chips, tags, the loop's tab) and the legend rule are decorative: the text inside
names each box.

#### Scenario: Text and marks stay readable in both themes
- **WHEN** text and marks are compared with what they sit on, in each theme
- **THEN** text clears 4.5:1, and connectors, arrowheads, lifelines, zones, and the loop frame clear 3:1
