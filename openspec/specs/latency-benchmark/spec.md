# latency-benchmark Specification

## Purpose
Defines the upload-to-draft latency benchmark and its median gate.

## Requirements

### Requirement: The benchmark reports the median upload-to-draft time
The latency benchmark SHALL run each benchmark case through the app from its first upload to an
appeal-ready draft, one case at a time, and SHALL write a typed `LatencyReport` with each case's
seconds, its per-step seconds, and the median. It SHALL exit non-zero when the median exceeds 10
minutes or a case did not finish.

#### Scenario: Latency benchmark reports the median
- **WHEN** the latency benchmark runs end to end from upload to draft on synthetic denial cases
- **THEN** it reports the median duration
- **AND** exits non-zero if the median exceeds 10 minutes

#### Scenario: Failures never lower the median
- **WHEN** a case fails before its draft
- **THEN** it counts as slower than every finished case and the gate fails
