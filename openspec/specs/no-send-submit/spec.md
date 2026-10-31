# no-send-submit Specification

## Purpose
Defines the checks that ClaimCoach has no send or submit capability: no pane control and no
backend route can transmit a draft or case content off this Mac.

## Requirements

### Requirement: No contribution offers send or submit
No contribution, settings page, or rendered control of the desktop half SHALL have a label,
title, ID, or command that sends, submits, faxes, e-mails, transmits, or uploads to a payer.

#### Scenario: No contribution offers send or submit
- **WHEN** plugin.js is loaded with a fake ctx and all registered contributions are collected
- **THEN** none has a label or command that sends or submits to a payer

### Requirement: No backend route transmits case content
No route of `plugin_api.py` or the worker SHALL send case content to a non-loopback destination;
every route of every type SHALL be pinned by a test, and the app package SHALL create HTTP
clients, sockets, and subprocesses only in reviewed modules that talk to loopback services or run
fixed local commands, with no mail, FTP, or raw HTTP client and no import by name at run time.

#### Scenario: No backend route transmits case content
- **WHEN** the plugin_api and worker route tables are enumerated
- **THEN** no route sends case content to a non-loopback destination

#### Scenario: A case's routes reach only loopback
- **WHEN** a case is created, extracted, diagnosed, drafted, edited, and exported through the gateway
- **THEN** every socket connect made goes to a loopback address
