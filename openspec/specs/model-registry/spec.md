# model-registry Specification

## Purpose
Defines the typed `models.yaml` registry that maps each ClaimCoach model role to its model
directory under `MODELS_HOME`, its venv, its server command, and its port.

## Requirements

### Requirement: Every PRD role is registered
The default `models.yaml` SHALL load into the typed `ModelRegistry` and SHALL contain the roles
extraction, phi_detection, classification, embedding, rerank, explanation, drafting, and
transcription. A file missing any role SHALL fail validation.

#### Scenario: Every PRD role is registered
- **WHEN** the default models.yaml is loaded into the typed ModelRegistry model
- **THEN** it contains all eight roles

#### Scenario: Missing role rejected
- **WHEN** a models.yaml omits the drafting role
- **THEN** loading fails with a validation error naming `roles`

### Requirement: Model paths stay under MODELS_HOME
Model and conversion-source directories SHALL be relative paths without `..`, and every resolved
model path SHALL be inside `MODELS_HOME`. Resolving paths SHALL NOT copy, move, or create any
file under `MODELS_HOME`.

#### Scenario: Model directories resolve under MODELS_HOME
- **WHEN** MODELS_HOME is set to a test directory and the registry resolves model paths
- **THEN** every model path is inside MODELS_HOME and no weight file is copied

#### Scenario: Escaping path rejected
- **WHEN** a model_dir is absolute or contains `..`
- **THEN** loading fails with a validation error naming that entry

### Requirement: Ports stay inside the app range
Every model server port SHALL be inside 18200–18219 and SHALL NOT be 18200, which belongs to the
worker. Two roles SHALL share a port only when they describe the same server.

#### Scenario: Ports outside the app range are rejected
- **WHEN** a models.yaml entry has port 18300
- **THEN** loading fails with a validation error naming that entry and the allowed range 18200-18219

#### Scenario: Conflicting shared port rejected
- **WHEN** two roles name the same port but different model directories
- **THEN** loading fails with a validation error naming both roles

### Requirement: Server commands bind loopback
Every server command SHALL contain the `{host}` and `{port}` placeholders, which the worker fills
with `127.0.0.1` and the role's port, and SHALL use no other placeholders than `{venv}`,
`{model}`, `{host}`, and `{port}`.

#### Scenario: Command without host rejected
- **WHEN** a command omits `{host}`
- **THEN** loading fails with a validation error naming that entry

### Requirement: Default file written on first run
On first run the worker SHALL write the packaged default `models.yaml` to the ClaimCoach data dir
and SHALL NOT overwrite an existing file.

#### Scenario: First run
- **WHEN** the data dir has no models.yaml
- **THEN** the default file is written there and loads into ModelRegistry

#### Scenario: Edited file kept
- **WHEN** the data dir already has a models.yaml
- **THEN** it is left unchanged
