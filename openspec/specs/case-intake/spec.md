# case-intake Specification

## Purpose
Defines how a biller creates a case and attaches source documents (uploaded files or pasted text).

## Requirements

### Requirement: Uploaded files are attached as source documents
`POST /cases` SHALL create an open case with an opaque `case_` ID in the active profile's user
scope, and `POST /cases/{case_id}/documents` SHALL attach the uploaded PDF, PNG, JPEG, or UTF-8
text file to that case, encrypted at rest; `GET /cases/{case_id}` SHALL list it as a source
document with its kind, filename, content type, and size.

#### Scenario: A PDF or image is attached to a new case
- **WHEN** the biller creates a case and drops in a PDF or image file
- **THEN** the case lists the file as an attached source document
- **AND** the stored bytes are encrypted and equal the uploaded bytes once decrypted

#### Scenario: The pane uploads a dropped file into the open case
- **WHEN** a file is dropped on the pane while a case is open
- **THEN** the pane uploads it into that case and shows it in the document list

### Requirement: Pasted text is attached as a source document
`POST /cases/{case_id}/paste` SHALL attach pasted text to the case, as kind `edi_835` when it is an
X12 835 interchange and `text` otherwise.

#### Scenario: Pasted 835 text is attached to a case
- **WHEN** the biller pastes 835 text into an open case
- **THEN** the case lists the pasted text as an attached source document of kind `edi_835`

### Requirement: Intake refuses what it cannot handle
The kind SHALL be decided from the bytes, not the filename or declared type. A file over 16 MiB or
pasted text over 4 MiB SHALL be refused with `document_too_large`; any other format with
`unsupported_document`; a closed or purged case with `case_closed`; an unknown case with
`case_not_found`. Every refusal SHALL be the error envelope, store nothing, and echo no content.

#### Scenario: An unsupported file is refused
- **WHEN** the biller drops a file whose bytes are not PDF, PNG, JPEG, or UTF-8 text
- **THEN** the answer is `unsupported_document` and the case lists no new document

#### Scenario: A file that is too large is refused
- **WHEN** the upload is larger than 16 MiB
- **THEN** the answer is `document_too_large` and nothing is stored
