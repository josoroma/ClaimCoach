# Spec Delta

## Purpose

Defines the installable ClaimCoach Hermes plugin folder: its v2 manifest, its backend manifest,
its typed settings schema, and the rule that its Python half loads only when the user enables it.

## ADDED Requirements

### Requirement: Manifest declares the v2 fields
The package SHALL ship `plugin.yaml` with `name: claimcoach`, `manifest_version: 2`,
`requires_hermes: ">=0.22.5"`, `python_runtime: external`, a `provides_tools` list, and a
`config_schema`, and Hermes plugin validation SHALL accept it.

#### Scenario: Validation succeeds
- **WHEN** the developer runs `hermes plugins validate plugin/`
- **THEN** validation succeeds
- **AND** the manifest declares `manifest_version` 2, `requires_hermes` ">=0.22.5", `python_runtime` external, `provides_tools`, and `config_schema`

### Requirement: Settings schema has one source of truth
The manifest `config_schema` SHALL equal the schema rendered from the typed ClaimCoach settings
model, and every default SHALL validate against that model.

#### Scenario: Manifest and settings model agree
- **WHEN** the manifest `config_schema` is compared with the schema rendered from the settings model
- **THEN** they are equal

#### Scenario: Invalid or unknown setting rejected
- **WHEN** settings declare a retention period outside 1–3650 days, an empty models home, or an unknown key
- **THEN** validation of the settings fails

### Requirement: Backend manifest points at plugin_api.py
`dashboard/manifest.json` SHALL contain `"name": "claimcoach"` and `"api": "plugin_api.py"`, and
`plugin_api.py` SHALL export a FastAPI `router`.

#### Scenario: Backend manifest read
- **WHEN** `dashboard/manifest.json` is read
- **THEN** it contains name "claimcoach" and api "plugin_api.py"

### Requirement: Python half inert until enabled
Hermes SHALL NOT register any `claimcoach_*` tool while `claimcoach` is absent from
`plugins.enabled`, and SHALL register exactly the tools listed in `provides_tools` once it is
enabled. Each registered tool SHALL return a JSON string.

#### Scenario: Not enabled
- **WHEN** the package is linked into the Hermes plugins directory and `claimcoach` is not in `plugins.enabled`
- **AND** Hermes discovers plugins
- **THEN** no `claimcoach_*` tool is registered

#### Scenario: Enabled
- **WHEN** `claimcoach` is in `plugins.enabled` and Hermes discovers plugins
- **THEN** the `claimcoach_*` tools listed in `provides_tools` are registered

#### Scenario: Placeholder tool answers with an error envelope
- **WHEN** a registered tool is called before its story is delivered
- **THEN** it returns the JSON error envelope with code `not_implemented`
