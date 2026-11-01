# corpus-import-page Specification

## Purpose
Defines how a manager previews and imports a global-corpus bundle from the ClaimCoach settings
page.

## Requirements

### Requirement: A bundle is previewed before it is imported
`POST /corpus/import/preview` SHALL validate the uploaded local bundle file and answer whether it
is valid, its first problem, its item counts per kind, the payers it names, its stale items, and
which global items it replaces (by kind and key), and SHALL write nothing.

#### Scenario: A bundle is previewed before it is imported
- **WHEN** the manager picks a local corpus bundle file on the settings page
- **THEN** the page shows what the bundle holds and which global items it replaces
- **AND** nothing is imported

### Requirement: The import runs only after confirmation
`POST /corpus/import` in the gateway SHALL import the uploaded bundle through the worker only with
`confirm=true`, and SHALL answer `import_not_confirmed` without it, sending nothing to the worker.

#### Scenario: The import runs only after confirmation
- **WHEN** the manager confirms the previewed import
- **THEN** the bundle is imported into the global corpus and the page shows what was stored

#### Scenario: An unconfirmed import
- **WHEN** the import route is called without confirm=true
- **THEN** it answers import_not_confirmed and the global corpus is unchanged

### Requirement: An invalid bundle is refused
A file that is not a valid bundle (suffix, size, YAML or JSON, or the bundle schema) SHALL be
previewed as invalid with its first problem, without echoing file text, and SHALL be refused by the
import route with `invalid_bundle`.

#### Scenario: An invalid bundle is refused
- **WHEN** the manager picks a file that is not a valid corpus bundle
- **THEN** the page says which part is invalid and nothing is imported
