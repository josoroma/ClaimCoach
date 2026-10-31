# memory-guard Specification

## Purpose
Defines which ClaimCoach model servers may be resident at the same time and how a load that would
break those rules waits.

## Requirements

### Requirement: Never two large models resident
A server whose size tier is at least the policy's large tier (14B) SHALL NOT start while another
large ClaimCoach server is starting, ready, or stopping. The blocked load SHALL wait, and an idle
large server that blocks it SHALL be unloaded.

#### Scenario: Two large models are never resident together
- **WHEN** the Qwen3-14B explanation server is resident and a drafting request needs Bonsai 27B
- **THEN** the drafting load waits until the 14B server is unloaded and the two are never resident at the same time

#### Scenario: Busy large server finishes first
- **WHEN** the explanation server is serving a request and a drafting request arrives
- **THEN** the explanation request completes before the explanation server is unloaded and drafting starts

#### Scenario: Queued load is not starved
- **WHEN** a drafting load is queued behind the explanation server and new explanation requests keep arriving
- **THEN** the new requests wait and drafting starts as soon as the current explanation request ends

#### Scenario: Conversion holds back loads
- **WHEN** the reranker conversion is running and a request needs any model
- **THEN** the load is queued until the conversion ends

### Requirement: Voxtral loads only alone
A server marked `runs_alone` SHALL start only when no other ClaimCoach model server is resident,
and no other server SHALL start while it is resident.

#### Scenario: Voxtral loads only alone
- **WHEN** any other ClaimCoach model server is resident and a transcription job needs Voxtral
- **THEN** the job is queued and Voxtral starts only after no other ClaimCoach model server is resident

### Requirement: Queued work reports its state
While a request waits on the memory guard, the role's model status SHALL report `queued` with the
number of waiting requests. A wait longer than the queue timeout SHALL fail with the `model_busy`
error envelope.

#### Scenario: Queued work reports its state
- **WHEN** a request is waiting on the memory guard and the desktop half polls the status
- **THEN** the status reports queued

#### Scenario: Queue timeout
- **WHEN** a blocked load waits longer than the queue timeout
- **THEN** the request fails with the model_busy envelope and the role no longer reports queued
