# model-acquisition Specification

## Purpose
Defines how ClaimCoach reports missing models and fetches or converts them only after explicit
user confirmation.

## Requirements

### Requirement: Missing models are reported
Model status SHALL report each role's weights as `missing` when its model directory under
`MODELS_HOME` does not hold a model (`config.json` and at least one `*.safetensors`), and
`present` otherwise.

#### Scenario: Missing models are reported
- **WHEN** a registered role's model directory does not exist under MODELS_HOME and the settings page requests model status
- **THEN** that role is reported as missing

### Requirement: Download requires confirmation
The worker SHALL run `hf download` into `MODELS_HOME` only for a request with `confirm: true`,
SHALL report the job while it runs, and SHALL report the role present once the files exist. A
request without `confirm` SHALL fail with `invalid_request`.

#### Scenario: Download requires confirmation
- **WHEN** a model is missing and the user confirms the download in settings
- **THEN** the worker runs hf download into MODELS_HOME and the role is reported present on success

#### Scenario: Missing confirmation flag
- **WHEN** a download request has no confirm field, a non-boolean confirm such as "yes", or a non-JSON content type
- **THEN** the response is the invalid_request envelope and no process starts

#### Scenario: Interrupted download
- **WHEN** a sharded model directory lacks a shard listed in its index
- **THEN** the role is reported missing, is not served, and a confirmed download resumes it

### Requirement: Declined download makes no network call
A request with `confirm: false` SHALL return `declined` and SHALL NOT start a process or open an
outbound network connection.

#### Scenario: Declined download makes no network call
- **WHEN** a model is missing and the user declines the download
- **THEN** no outbound network connection is opened

### Requirement: No conversion route or command remains
The gateway, the worker, and the Makefile SHALL offer no model conversion: no `models/convert`
route, no `models-convert` target, and no `conversion_unavailable` error code.

#### Scenario: No conversion route or command remains
- **WHEN** the gateway's and the worker's routes and the Makefile's targets are listed
- **THEN** there is no models/convert route and no models-convert target
