# quality-gate Specification

## Purpose
Defines the one quality-gate command every ClaimCoach story must pass before review, the offline
test guarantee, and the import and registration contract of the desktop plugin.

## Requirements

### Requirement: One gate command
`make check` SHALL run ruff check, ruff format --check, mypy --strict, biome check,
tsc --noEmit --checkJs, the offline pytest suite, and the desktop node tests, and SHALL exit 0 only
when all of them pass. Python and desktop line coverage below 100% SHALL fail the gate.

#### Scenario: make check passes on a clean tree
- **WHEN** the developer runs `make check` on a clean checkout with dev dependencies installed
- **THEN** every listed tool runs and the command exits 0

#### Scenario: A type error fails the gate
- **WHEN** a Python function's return annotation contradicts its return value and the developer runs `make check`
- **THEN** the command exits non-zero and its output names the mypy error

### Requirement: plugin.js is type-checked against the SDK stub
`desktop/plugin.js` SHALL begin with `// @ts-check` and SHALL type-check with zero errors against
the checked-in `types/hermes-plugin-sdk.d.ts`.

#### Scenario: Type check
- **WHEN** `tsc --noEmit --checkJs` runs on `desktop/plugin.js`
- **THEN** it reports zero errors

### Requirement: plugin.js registration contract
The default export SHALL be an opt-in plugin with id `claimcoach` whose `register(ctx)` records the
case pane, the manager dashboard route, a sidebar nav entry, a right statusbar item, and a settings
page when the host supports settings pages.

#### Scenario: plugin.js registers its contributions against a fake ctx
- **WHEN** `register(ctx)` is called with a fake ctx under `node --test`
- **THEN** the pane, route, statusbar, and settings contributions are recorded

#### Scenario: Older host without settings pages
- **WHEN** the fake ctx has no `registerSettingsPage`
- **THEN** registration still succeeds without a settings page

### Requirement: plugin.js imports only allowed specifiers
Every import specifier in `desktop/plugin.js` SHALL be one of `@hermes/plugin-sdk`, `react`, or
`react/jsx-runtime`.

#### Scenario: Import scan
- **WHEN** the import-scan test runs on `desktop/plugin.js`
- **THEN** every import specifier is one of the three allowed specifiers

### Requirement: Offline tests never leave loopback
The offline suite SHALL use the fake OpenAI-compatible model server, and any attempt to connect to
or resolve a non-loopback address during it SHALL fail the test.

#### Scenario: Offline tests use the fake model server
- **WHEN** the offline suite runs with `-m "not models"`
- **THEN** model calls reach the fake server on loopback
- **AND** a connection attempt to a non-loopback address fails with a socket-guard error
