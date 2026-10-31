# model-lifecycle Specification

## Purpose
Defines how the worker runs local model servers: started lazily per role, used only while
healthy, stopped when idle, and reported through a typed status.

## Requirements

### Requirement: Lazy start on first use
The worker SHALL NOT start any model server at startup. When a request needs a role whose server
is not running, the worker SHALL start the configured command on `127.0.0.1` and the role's port
and SHALL serve the request only after `GET /v1/models` reports healthy.

#### Scenario: A role's server starts on first use
- **WHEN** no model server for the classification role is running and the worker receives a request needing that role
- **THEN** the worker starts the configured server and serves the request once /v1/models reports healthy

#### Scenario: Shared server started once
- **WHEN** phi_detection and classification share a port and both are used
- **THEN** exactly one server process runs for that port

### Requirement: Unhealthy servers are not used
A server whose `/v1/models` check fails SHALL NOT be used. The request SHALL fail with the
`model_unavailable` error envelope, the server process SHALL be stopped, and the role's status
SHALL report `unhealthy`. A port already in use by another process SHALL NOT be adopted.

#### Scenario: An unhealthy server is not used
- **WHEN** a model server's /v1/models check fails and the worker needs that role
- **THEN** the request fails with the error envelope and the model status reports unhealthy

#### Scenario: Port taken by another process
- **WHEN** the role's port is already bound by a process ClaimCoach did not start
- **THEN** the request fails with the error envelope and no process is signalled

### Requirement: Idle servers are unloaded
The idle sweep SHALL stop every server that no request is using and that has not been used for
longer than the configured idle timeout, and the role's status SHALL then report `unloaded`.

#### Scenario: Idle servers are unloaded
- **WHEN** a running server has had no requests for longer than the idle timeout and the idle sweep runs
- **THEN** the server process is stopped and the model status reports unloaded

#### Scenario: Busy servers are kept
- **WHEN** a request is still using the server when the idle sweep runs
- **THEN** the server keeps running

#### Scenario: Request racing an idle stop
- **WHEN** an idle stop and a new request reach the server at the same moment
- **THEN** the request is served by a running server and never by one being stopped

### Requirement: Cancelled requests leave no state behind
A request cancelled while its server starts SHALL stop the half-started process and leave the role
`unloaded`, and a request cancelled at any point SHALL release its hold on the server.

#### Scenario: Caller times out during a start
- **WHEN** a request is cancelled while the role's server is starting
- **THEN** the process is stopped, the role reports unloaded, and later requests for any role are admitted normally

### Requirement: Worker owns its model servers
The worker SHALL stop every model server it started when it shuts down, and on start SHALL stop a
server recorded by a previous worker only if that PID still runs the recorded command.

#### Scenario: Worker shutdown
- **WHEN** the worker stops, even during a model load
- **THEN** no model server it started is still running

#### Scenario: Orphans after a crash
- **WHEN** a previous worker was killed and left servers running
- **THEN** the next worker start stops each one whose command line still shows its model path and port, and signals no other process
