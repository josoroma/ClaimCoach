# Spec Delta

## Purpose

Defines the registered ClaimCoach case pane (case list and case detail views), the manager
dashboard route, and how the pane renders backend errors.

## ADDED Requirements

### Requirement: The case pane is registered with list and detail views
`register(ctx)` SHALL register a pane contribution whose render shows a case list view and a case
detail view, built with `jsx()`/`jsxs()` only.

#### Scenario: The case pane is registered
- **WHEN** register(ctx) runs with a fake ctx
- **THEN** a pane contribution with the case list and case detail views is registered

#### Scenario: A listed case opens in the detail view
- **WHEN** the biller selects a case in the list
- **THEN** the detail view opens that case

### Requirement: The dashboard route is registered
`register(ctx)` SHALL register a route contribution at `/claimcoach/dashboard` rendering the
manager dashboard, with a sidebar entry to it.

#### Scenario: The dashboard route is registered
- **WHEN** register(ctx) runs with a fake ctx
- **THEN** a route contribution for the manager dashboard is registered

### Requirement: The case list holds no case content
`GET /cases` SHALL answer the active profile's newest cases (at most 200) with IDs, dates,
outcome, counts, and step flags only, SHALL not be audited, and SHALL answer an empty list for a
profile without a user scope.

#### Scenario: The list of cases
- **WHEN** the pane reads the case list
- **THEN** each case shows its ID, dates, and steps, and no document text, payer, or claim number

### Requirement: Backend errors render as an error state
A rejected list read SHALL render a fixed error state with a Retry button; the pane SHALL never
throw or show envelope text.

#### Scenario: Backend errors render as an error state
- **WHEN** ctx.rest returns the error envelope while the case pane loads
- **THEN** the pane shows an error state instead of throwing
