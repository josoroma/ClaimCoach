# phi-free-telemetry Specification

## Purpose
Defines how ClaimCoach writes logs and plugin events so that diagnostics never contain PHI or
document text.

## Requirements

### Requirement: Logs are structured JSON with a request or job ID
The worker SHALL write every log line as one JSON object with `ts`, `level`, `logger`, `message`,
`request_id`, and `job_id`, and at least one of `request_id` and `job_id` SHALL be set.

#### Scenario: Logs are structured JSON without document text
- **WHEN** a case built from a synthetic document with seeded PHI is processed end to end
- **THEN** every log line is valid JSON with a request or job ID
- **AND** no log line contains a seeded PHI string or document text

### Requirement: Log records are scrubbed of PHI
Every ClaimCoach log record SHALL be scrubbed with the regex validators and the values the
redactor found in the process before it is written, and exception messages and tracebacks SHALL
NOT be written (only the exception type).

#### Scenario: Careless log call
- **WHEN** pipeline code logs a message that quotes a patient name the redactor found and an SSN
- **THEN** the written line shows placeholders instead of the name and the SSN

#### Scenario: Exception quoting a document
- **WHEN** an exception whose message contains document text is logged with its traceback
- **THEN** the line carries the exception type and no part of the message or traceback

### Requirement: Event payloads carry no PHI
Plugin event payloads SHALL be typed models whose string fields are enums or opaque IDs generated
by ClaimCoach (`case_` or `job_` followed by 16 lowercase hex digits), sent with
`broadcast_plugin_event("claimcoach", <event>, payload)`.

#### Scenario: Broadcast events carry no PHI
- **WHEN** progress events are broadcast for a case built from a synthetic document with seeded PHI
- **THEN** no event payload contains a seeded PHI string

#### Scenario: Free text is rejected
- **WHEN** an event is built with a name, a date, an SSN, an MRN, a member ID, or document text in any field
- **THEN** validation fails and nothing is sent

### Requirement: Logging failures never write PHI
A log call whose arguments do not fit its format, a failing handler, and an uncaught exception
SHALL each produce at most one JSON line without the arguments, the exception message, or a
traceback, and SHALL NOT raise into the code that logged.

#### Scenario: Unformattable log call
- **WHEN** code logs a format string with arguments of the wrong type that contain PHI
- **THEN** one JSON line with the scrubbed format string is written and the caller continues
