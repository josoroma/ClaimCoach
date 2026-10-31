# phi-redaction Specification

## Purpose
Defines how ClaimCoach finds PHI in a text by category and produces a redacted text, using the
local PHI model and regex validators.

## Requirements

### Requirement: Detected spans carry a category
The redactor SHALL return typed `PhiSpan` results, each with a `PhiCategory`. Spans SHALL be the
union of the PHI model's spans (located at every occurrence of each verbatim value) and the regex
validators' spans for SSN, MRN, DOB, phone, and member ID.

#### Scenario: Detected spans carry a category
- **WHEN** the redactor runs on a synthetic document containing a name, DOB, MRN, member ID, SSN, address, and phone
- **THEN** it returns typed PhiSpan results whose categories cover each of those seven types

#### Scenario: Values the model invents are ignored
- **WHEN** the model reports a value that does not occur in the document
- **THEN** no span is produced for it

### Requirement: Redacted text replaces each span
`redact()` SHALL replace each merged span with its category placeholder, SHALL redact every other
occurrence of each detected value and of each word of a detected name, and SHALL run the regex
validators again over its output and redact anything they find.

#### Scenario: Redacted text replaces each span
- **WHEN** redact() is applied to a document with its detected spans
- **THEN** none of the seeded PHI strings appear in the output text

#### Scenario: Second pass catches PHI the spans missed
- **WHEN** redact() is given spans that omit a regex-detectable value
- **THEN** the value is redacted and counted as a second-pass hit

### Requirement: Redaction fails closed
When the PHI model is unavailable or its reply is truncated or not the expected JSON, redaction
SHALL fail with an error and SHALL NOT return text.

#### Scenario: Unusable model reply
- **WHEN** the worker's /redact route receives a model reply that is not the expected JSON
- **THEN** it answers 503 with the redaction_failed envelope and no text

### Requirement: Prompts keep the document as data
The detector SHALL build its prompt with the prompt builder so that the document appears only in
the data section.

#### Scenario: Document with an injected instruction
- **WHEN** the detector sends a document containing "Ignore previous instructions"
- **THEN** the system message and the instruction text contain none of the document

### Requirement: Redaction is robust to layout and adversarial input
A model value SHALL match its occurrences across line breaks and punctuation changes, a value
that cannot be located SHALL contribute its distinctive words, and no input SHALL make a
validator run for more than a fraction of a second.

#### Scenario: Address rewritten by the model
- **WHEN** the model reports an address on one line that the document wraps over two lines
- **THEN** the two-line address is redacted

#### Scenario: Long whitespace after a label
- **WHEN** a document has 10 000 spaces, underscores, or newlines after a label
- **THEN** the validators finish in under half a second
