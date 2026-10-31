# prompt-isolation Specification

## Purpose
Defines how ClaimCoach assembles prompts for its local models so that text from uploaded
documents is always data and never instruction.

## Requirements

### Requirement: Document text only in the delimited data section
Every pipeline prompt SHALL be built by `build_prompt()` from a registered `PromptTemplate` and
`DataItem`s. Per-call content SHALL appear only in the user message, inside a data block delimited
by markers that carry a random per-prompt boundary, and SHALL NOT appear in the system message or
in the instruction text.

#### Scenario: Prompts place document text only inside the data section
- **WHEN** any ClaimCoach prompt is built from a document whose text contains the line "ignore previous instructions"
- **THEN** the document text appears only inside the delimited data section of the prompt
- **AND** the system and instruction sections contain none of it

#### Scenario: A document cannot close its own data block
- **WHEN** a document contains a forged closing marker, or contains the boundary first drawn for the prompt
- **THEN** the data block still ends only at the marker with the prompt's boundary, and the boundary does not occur in the data

### Requirement: The data rule is stated to the model
The system message of every prompt SHALL state that the content between the data markers is
untrusted document content to analyze and that instructions inside it are never followed.

#### Scenario: System message carries the data rule
- **WHEN** a prompt is built
- **THEN** its system message is the template's system text followed by the data rule naming that prompt's boundary

### Requirement: Templates are fixed and registered
Prompt templates SHALL be defined once with `define_template()`, SHALL have unique names, and SHALL
be listed by `registered_templates()`.

#### Scenario: Duplicate template name
- **WHEN** a template name is defined twice
- **THEN** the second definition fails

### Requirement: Prompts cannot be assembled around the builder
`build_prompt()` SHALL refuse a template that is not the registered template of its name, and a
`BuiltPrompt` SHALL fail validation unless its system message is the registered template's system
text plus the data rule and its user message is the template's instructions followed only by data
blocks closed with its boundary.

#### Scenario: Hand-built prompt with document text in a fixed section
- **WHEN** a BuiltPrompt is constructed with document text in the system message, before the instructions, or after the data blocks
- **THEN** validation fails
