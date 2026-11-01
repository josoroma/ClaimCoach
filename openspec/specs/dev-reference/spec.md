# dev-reference Specification

## Purpose
Defines the reference README-DEV.md gives for the REST API, the database, storage, and uploads, and how it is kept true to the code.

## Requirements

### Requirement: Every gateway route is documented
README-DEV.md SHALL list every route mounted at `/api/plugins/claimcoach/` with its method, path, request, and response model, and a test SHALL fail when the route set or a response model differs.

#### Scenario: Every gateway route is documented
- **WHEN** README-DEV.md is read against the gateway router
- **THEN** each route is listed with its method, path, request body, and response model
- **AND** a test fails when a route is added, removed, or changes its response model without the guide

### Requirement: Every table is documented with its writers and readers
Each table of the corpus schema SHALL be listed with all its columns, what writes it, what reads it, and whether it holds PHI.

#### Scenario: Every table is documented with its writers and readers
- **WHEN** README-DEV.md is read against the corpus schema
- **THEN** each table and index table is listed with its columns, what writes it, and what reads it
- **AND** a test fails when a table is missing from the guide

### Requirement: Uploads are documented with the limits the code enforces
Each upload (document, paste, call recording, corpus bundle) SHALL be listed with its route, accepted types, and size limit, equal to the code's constants.

#### Scenario: Uploads are documented with the limits the code enforces
- **WHEN** README-DEV.md is read against the upload limits
- **THEN** each upload lists its route, accepted types, and size limit
- **AND** the limits in the guide equal the limits in the code

### Requirement: Every place ClaimCoach stores data is documented
Each storage location SHALL be listed with its path, contents, whether it holds PHI, and its protection.

#### Scenario: Every place ClaimCoach stores data is documented
- **WHEN** README-DEV.md is read against the path modules
- **THEN** each location is listed with its path, what it holds, whether it holds PHI, and how it is protected
