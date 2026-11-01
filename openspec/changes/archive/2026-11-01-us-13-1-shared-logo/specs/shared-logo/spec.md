# Spec Delta

## Purpose

Defines ClaimCoach's logo file and how the desktop pages show it, so the pages and the READMEs use
one mark.

## ADDED Requirements

### Requirement: One self-contained logo file
`plugin/assets/claimcoach-logo.svg` SHALL be an SVG document with a `title`, a `viewBox`, and only
`rect` and `path` shapes, and SHALL contain no script, event handler, external or `href`
reference, embedded image, or `@import`.

#### Scenario: One logo file is the source of the mark
- **WHEN** `plugin/assets/claimcoach-logo.svg` is parsed
- **THEN** it is a self-contained SVG with a title, a viewBox, and no script, external reference, or embedded image

### Requirement: The plugin pages show the shared logo
The case pane, the manager dashboard, and the settings page SHALL each draw the logo at the start
of their heading, with exactly the shapes and colors of the logo file.

#### Scenario: The plugin pages show the shared logo
- **WHEN** the case pane, the manager dashboard, and the settings page render
- **THEN** each shows the ClaimCoach logo next to its heading
- **AND** the logo's shapes and colors are the ones in `plugin/assets/claimcoach-logo.svg`

### Requirement: The logo is hidden from screen readers
The drawn logo SHALL be `aria-hidden` and not focusable, so the heading's text names the page.

#### Scenario: The logo does not repeat the heading to screen readers
- **WHEN** a screen reader reads a plugin page with the logo next to its heading
- **THEN** the logo is hidden from it and the heading names the page
