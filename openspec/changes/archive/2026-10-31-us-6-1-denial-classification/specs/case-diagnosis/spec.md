# Spec Delta

## Purpose

Defines how an extracted case is diagnosed: the denial reason from a closed set, the appeal
likelihood with its reasons, the diagnosis job, and how the pane shows the result.

## ADDED Requirements

### Requirement: Classification returns a typed result
Diagnosing a case SHALL send its extracted facts and the global corpus's notes for its codes to
the `classification` role through the registered `classification` prompt template, and SHALL store
a `Diagnosis` whose denial reason is one of `eligibility`, `prior_authorization`,
`medical_necessity`, `coding_error`, `missing_information`, `duplicate_claim`, `timely_filing`,
`non_covered_service`, `bundling`, `coordination_of_benefits`, or `other`, and whose appeal
likelihood is `low`, `medium`, or `high`. A reply that does not validate SHALL end the job
`failed` with `diagnosis_failed` and leave any previous diagnosis unchanged.

#### Scenario: Classification returns a typed result
- **WHEN** diagnosis runs on an extracted case
- **THEN** the result validates against the typed Diagnosis model with a denial reason and an appeal likelihood of low, medium, or high

#### Scenario: A reply outside the closed set
- **WHEN** the classification model answers with a denial reason that is not in the set
- **THEN** the job ends failed with diagnosis_failed and no diagnosis is stored

### Requirement: Appeal likelihood includes reasons
A diagnosis SHALL hold one to five non-blank reasons for its appeal likelihood, and the case and
the pane SHALL show the likelihood with every reason.

#### Scenario: Appeal likelihood includes reasons
- **WHEN** the biller views a diagnosed case
- **THEN** the appeal likelihood is shown with at least one reason

### Requirement: Diagnosis runs as a job after extraction
`POST /cases/{case_id}/diagnose` SHALL start a diagnosis job, refused with `not_extracted` when
the case has no extraction; progress SHALL be relayed as `plugin.claimcoach.case.progress` events
(`classifying`, then `done` or `failed`). A case SHALL run at most one job of either kind at a
time: a request while a job runs SHALL return that job, whatever its kind. The pane SHALL start a
diagnosis when an extraction job ends `done` and no field needs confirmation, and SHALL follow a
job's events from before its start request is sent.

#### Scenario: Diagnosis before extraction
- **WHEN** diagnosis is requested for a case that has not been extracted
- **THEN** the request is refused with not_extracted and no job starts

#### Scenario: Diagnosis requested during the first extraction
- **WHEN** diagnosis is requested while the case's first extraction job runs
- **THEN** the running extraction job is returned with its kind instead of a refusal

#### Scenario: The pane diagnoses after extraction
- **WHEN** an extraction job ends done and every field was read
- **THEN** the pane starts the case's diagnosis and shows its progress

#### Scenario: Fields to confirm wait for the biller
- **WHEN** an extraction job ends done with a field that needs confirmation
- **THEN** the pane shows the case without diagnosing it, and the biller confirms the field and then presses Diagnose case

#### Scenario: A diagnosis that fails before its start is answered
- **WHEN** a diagnosis job ends failed before the pane receives the answer to its start request
- **THEN** the pane shows the case with the failure's explanation instead of waiting

### Requirement: A stale diagnosis is flagged
The case SHALL report `diagnosis_stale` when its extraction changed after the diagnosis ran (a
confirmed field or a new extraction), and the pane SHALL ask the biller to diagnose again.

#### Scenario: A confirmed field makes the diagnosis stale
- **WHEN** the biller confirms a field after the case was diagnosed
- **THEN** the case reports its diagnosis as stale until diagnosis runs again
