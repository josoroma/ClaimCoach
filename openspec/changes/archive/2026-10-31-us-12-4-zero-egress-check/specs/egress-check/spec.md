# Spec Delta

## Purpose

Defines how ClaimCoach records attempts to reach beyond loopback and proves that a full case flow
makes none.

## ADDED Requirements

### Requirement: The worker records every non-loopback attempt
The worker SHALL install a socket audit hook before it loads its registry and SHALL append each
`socket.connect`, `socket.sendto`, or `socket.getaddrinfo` naming a non-loopback address to
`worker/egress.jsonl` (mode 0600) with its time, process, PID, event, host, and port only. Loopback
and Unix-socket traffic SHALL NOT be recorded.

#### Scenario: A non-loopback attempt is recorded
- **WHEN** worker code attempts to connect to 192.0.2.10:443
- **THEN** a record with event `connect`, host `192.0.2.10`, and port 443 is appended

#### Scenario: Loopback is not recorded
- **WHEN** the worker connects to a model server on 127.0.0.1
- **THEN** nothing is recorded

#### Scenario: A record that cannot be written does not break the call
- **WHEN** the record file cannot be written (a full disk)
- **THEN** the socket call goes on and `GET /egress` counts the attempt as dropped

### Requirement: The check refuses a worker that is not recording
The egress check SHALL exit 2 without running the flow when the worker's `GET /egress` says its
audit is off, and SHALL report a finding when the worker's dropped count grows during the flow.

#### Scenario: A worker started before the audit existed
- **WHEN** the running worker answers `audit: false`
- **THEN** the check exits 2 and says to restart the worker

### Requirement: A full case flow opens no non-loopback connection
The egress check SHALL run one case from upload through extraction, diagnosis, draft, and export
through the `plugin_api` router, while recording the router's own attempts, reading the worker's
records appended meanwhile, and sampling the worker's and every model server's connections with
`lsof`. It SHALL pass only when the flow completed and no non-loopback connection or attempt was
seen, and SHALL refuse to run while a model download or conversion is in progress or a case
model's weights are missing.

#### Scenario: A full case flow makes no non-loopback connection
- **WHEN** all required models are present, no download or import is in progress, and a case is processed from upload through draft and export
- **THEN** no network connection to a non-loopback address is opened by the worker, plugin_api, or model servers
- **AND** the check exits 0 and writes `evidence/US-12.4/egress.json`

#### Scenario: A connection beyond loopback fails the check
- **WHEN** an `lsof` sample shows a model server connected to a public address during the flow
- **THEN** the check exits non-zero and names the process, the address, and the port

#### Scenario: A download in progress is not measured
- **WHEN** a role is downloading
- **THEN** the check exits 2 without running the flow
