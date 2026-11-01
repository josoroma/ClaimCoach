# Spec Delta

## Purpose

The settings schema lists only what ClaimCoach reads.

## MODIFIED Requirements

### Requirement: Settings schema has one source of truth
The manifest `config_schema` SHALL equal the schema rendered from the typed ClaimCoach settings
model, every default SHALL validate against that model, and neither SHALL declare `models_home`.

#### Scenario: Manifest and settings model agree
- **WHEN** the manifest `config_schema` is compared with the schema rendered from the settings model
- **THEN** they are equal

#### Scenario: Invalid or unknown setting rejected
- **WHEN** settings declare a retention period outside 1–3650 days, a richer agent access that is not a boolean, or an unknown key
- **THEN** validation of the settings fails

## ADDED Requirements

### Requirement: A saved models_home is ignored
Loading a profile's settings SHALL drop a stored `models_home` before validation, so the other
saved settings keep their values; any other unknown key SHALL still reset them to the defaults.

#### Scenario: The setting is removed
- **WHEN** the settings schema is read
- **THEN** it has no models_home setting
- **AND** the worker still takes the weights folder from MODELS_HOME

#### Scenario: A saved models_home does not reset the other settings
- **WHEN** ClaimCoach loads the settings of a profile that saved models_home with its other settings
- **THEN** models_home is ignored and every other saved setting keeps its value
