# Spec Delta

## Purpose

Defines the REST contract the ClaimCoach desktop half sees at `/api/plugins/claimcoach/`: every
route returns a typed success body or the error envelope, and worker failures never leak stack
traces or document text.

## ADDED Requirements

### Requirement: Health route proxies to the worker
`GET /api/plugins/claimcoach/health` SHALL call the worker's health route with the current bearer
token and return a body that validates against the typed health model.

#### Scenario: Health route proxies to a running worker
- **WHEN** the worker is running and the desktop half calls `GET /api/plugins/claimcoach/health`
- **THEN** the response is 200 and validates against the typed health model

### Requirement: Worker traffic never uses a proxy
Calls from the gateway to the worker SHALL go directly to loopback and SHALL ignore proxy
settings in the environment, so the bearer token and case content never reach a proxy.

#### Scenario: Proxy configured in the environment
- **WHEN** `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` point at a proxy and the desktop half calls `GET /api/plugins/claimcoach/health`
- **THEN** the call reaches the worker directly and returns 200

### Requirement: Failures use the error envelope
Every failure SHALL return `{"ok": false, "error": {"code", "message"}}` with a non-empty code from
a fixed set and a fixed, PHI-free message.

#### Scenario: Worker unavailable returns the error envelope
- **WHEN** the worker is not running and the desktop half calls `GET /api/plugins/claimcoach/health`
- **THEN** the response is 503 with the error envelope and code `worker_unavailable`

#### Scenario: Worker token not yet issued
- **WHEN** the worker token file does not exist
- **THEN** the response is 503 with code `worker_unavailable`

#### Scenario: Worker returns an invalid body
- **WHEN** the worker answers 200 with a body that does not match the health model
- **THEN** the response is 502 with code `invalid_worker_response`

### Requirement: Unhandled worker errors are mapped, not leaked
A worker failure SHALL be mapped to the envelope, and the response SHALL contain no stack trace and
no text from the worker's exception.

#### Scenario: Worker raises an unexpected exception
- **WHEN** the worker raises an unexpected exception on a route
- **THEN** the proxy responds 502 with code `worker_error`
- **AND** the body contains no stack trace or document text

#### Scenario: Worker rejects the token
- **WHEN** the worker responds 401 with its envelope
- **THEN** the proxy responds 401 with code `unauthorized` and its own fixed message
