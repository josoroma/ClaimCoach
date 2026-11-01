# dev-guide Specification

## Purpose
Defines what README-DEV.md says about models, install, configuration, and the daily start, and how it is kept true to the code.

## Requirements

### Requirement: Every model role is documented from the registry
README-DEV.md SHALL list each role of the default `models.yaml` with its model folder, source repository, venv, port, size tier, and use, and a test SHALL fail when any of them differs from the registry.

#### Scenario: Every model role is documented from the registry
- **WHEN** README-DEV.md is read against the default models.yaml
- **THEN** each role is listed with its model folder, source repository, venv, port, size tier, and what ClaimCoach uses it for
- **AND** a test fails when a role, folder, venv, or port in the guide differs from the registry

### Requirement: The first run is a sequence of existing make targets
Every command of the first-run section SHALL be a Makefile target or a `hermes` command, and the section SHALL end with `make start` (which checks the worker's health) and `make models-status`.

#### Scenario: The first run is a sequence of existing make targets
- **WHEN** a developer follows the first-run section
- **THEN** every command in it is a make target that exists in the Makefile or a hermes command
- **AND** the section ends by checking the worker's health and the models' status

### Requirement: The daily start is separate from the first run
The start section SHALL start the worker, check it, and stop it, with no install, download, or link step.

#### Scenario: The daily start is separate from the first run
- **WHEN** a developer with ClaimCoach installed reads the start section
- **THEN** it starts the worker, checks it, and stops it, with no install step

### Requirement: Every setting and override is documented
Each `config_schema` setting SHALL be listed with its default and meaning, and each environment variable of the Makefile's first `?=` block SHALL be listed.

#### Scenario: Every setting and override is documented
- **WHEN** README-DEV.md is read against plugin.yaml and the Makefile
- **THEN** each setting is listed with its default and meaning
- **AND** a test fails when a setting is missing from the guide
