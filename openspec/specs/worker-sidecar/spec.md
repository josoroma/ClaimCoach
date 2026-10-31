# worker-sidecar Specification

## Purpose
Defines the app-owned ClaimCoach worker process that runs heavy work outside the Hermes gateway:
where it listens, how its per-launch bearer token is issued and stored, and how it rejects callers
without that token.

## Requirements

### Requirement: Worker binds to loopback only
The worker SHALL listen on `127.0.0.1`, by default on port 18200, and SHALL NOT listen on any
other interface. Configuration that names another host or a port outside 18200–18219 SHALL be
rejected before the process starts.

#### Scenario: Worker binds to loopback on the first port of the range
- **WHEN** the worker starts with the default configuration
- **THEN** it listens on 127.0.0.1:18200 and on no other interface

#### Scenario: Non-loopback host rejected
- **WHEN** the worker configuration names host `0.0.0.0`
- **THEN** configuration validation fails and no process starts

### Requirement: Per-launch bearer token
Each worker start SHALL write a new random bearer token to `worker/token` under the
profile-independent ClaimCoach plugin data dir (`<hermes root>/plugin-data/claimcoach`, which is
`plugin_data_dir("claimcoach")` for the default profile), readable and writable only by the owner
(mode 0600), and different from the token of the previous launch. One worker serves every Hermes
profile on the Mac, so the gateway of any profile and the operator commands SHALL resolve the same
token file.

#### Scenario: Worker writes a per-launch token in the plugin data dir
- **WHEN** the worker is stopped and then started
- **THEN** a token file exists under the plugin data dir with mode 0600
- **AND** its token differs from the token of the previous launch

### Requirement: Requests without the token are rejected
Every worker route, including paths with no handler, SHALL respond 401 with the error envelope
`{"ok": false, "error": {"code", "message"}}` when the bearer token is missing or wrong.

#### Scenario: Missing token
- **WHEN** a request reaches any worker route without the bearer token
- **THEN** the worker responds 401 with the error envelope

#### Scenario: Wrong token
- **WHEN** a request carries a bearer token from a previous launch
- **THEN** the worker responds 401 with the error envelope

#### Scenario: Framework errors
- **WHEN** an authenticated request hits an unknown path, a wrong method, or fails parameter validation
- **THEN** the worker responds with the error envelope (`not_found` or `invalid_request`) and never echoes the request input

### Requirement: Unhandled worker errors return a generic envelope
An unhandled exception in a worker route SHALL produce HTTP 500 with the error envelope code
`internal_error` and a fixed message that contains no exception text or stack trace.

#### Scenario: Route raises
- **WHEN** a worker route raises an exception whose message contains document text
- **THEN** the response is 500 with code `internal_error` and the body does not contain that text
- **AND** the worker log records only the exception type, method, and path

### Requirement: Launcher never adopts an unrelated process
`status` and `stop` SHALL treat a PID file as a running worker only when that PID is a live
ClaimCoach worker process, and SHALL never signal any other process. The worker log SHALL be
created with mode 0600.

#### Scenario: Reused PID
- **WHEN** the PID file names a live process that is not a ClaimCoach worker
- **THEN** `status` reports no worker, removes the PID file, and `stop` sends no signal
