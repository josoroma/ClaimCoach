# Spec Delta

## Purpose

With the conversion gone, only model servers hold back a large load.

## REMOVED Requirements

### Requirement: Never two large models resident
**Reason**: Its "Conversion holds back loads" scenario went with the conversion (US-14.1); the rest is restated below as "Two large models are never resident".
**Migration**: None: loads behave as before without a conversion running.

## ADDED Requirements

### Requirement: Two large models are never resident
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
