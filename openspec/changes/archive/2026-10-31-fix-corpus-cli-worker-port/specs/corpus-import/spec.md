# Spec Delta

## Purpose

Lets the corpus commands reach a worker started on a port other than the default.

## ADDED Requirements

### Requirement: Corpus commands reach the worker on the operator's port
The worker-backed corpus commands (`import`, `list`, `status`, `reindex`, `purge`, `audit`) SHALL
accept `--port` (default 18200) and send their requests to `127.0.0.1` on that port, and only
when the launcher recorded the running worker on that port; otherwise they SHALL answer
`worker_unavailable` without sending the token. A port outside 18200–18219 SHALL be refused
before any request is sent. The six worker-backed targets (`corpus-status`, `corpus-import`,
`corpus-list`, `corpus-reindex`, `corpus-purge`, `corpus-audit`) SHALL pass `WORKER_PORT` as that
port; the local targets (`corpus-backup`, `corpus-restore`, `corpus-key-export`,
`corpus-key-import`) SHALL pass none.

#### Scenario: A worker on another port
- **WHEN** the worker runs on port 18213 and the operator runs make corpus-list WORKER_PORT=18213
- **THEN** the corpus view is listed from that worker

#### Scenario: A port where the worker does not run
- **WHEN** the worker runs on 18200 and the operator runs a corpus command with --port 18205
- **THEN** the command answers worker_unavailable and nothing is sent to port 18205

#### Scenario: A port outside ClaimCoach's range
- **WHEN** the operator runs a corpus command with --port 80
- **THEN** the command stops with a usage error and exit 2, and nothing is sent
