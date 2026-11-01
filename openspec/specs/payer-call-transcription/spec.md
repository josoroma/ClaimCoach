# payer-call-transcription Specification

## Purpose
Defines how a biller attaches a recorded payer call to a case, how the call is queued for and
transcribed in the after-hours window by the local Voxtral server, and how the reference number
and the rep's instructions reach the case.

## Requirements

### Requirement: An attached call is queued for transcription
Submitting a case's attached call recording for transcription SHALL queue one
`TranscriptionJob` for the after-hours window of the case's profile and SHALL answer with the job
in state `queued`, the window, and the time the job may start. A call that already has a queued
or running job SHALL answer with that job; a closed case SHALL be refused with `case_closed`, and
an unknown call with `call_not_found`.

#### Scenario: An attached call is queued for transcription
- **WHEN** the biller submits a case's attached call recording for transcription
- **THEN** a transcription job is queued for the after-hours window
- **AND** the case shows the call with its job in state queued

#### Scenario: Submitting a queued call again
- **WHEN** the biller submits a call whose transcription job is still queued
- **THEN** the same job is answered and no second job is queued

### Requirement: Call recordings are typed and checked
Attaching a call SHALL accept one `multipart/form-data` part named `file` holding WAV, MP3, FLAC,
or M4A audio, decided from its bytes, of at most 128 MiB; it SHALL be sealed into the case as a
`call` item (audited `call_added`). Other bytes SHALL be refused with `unsupported_audio`, a larger
file with `call_too_large`, and a closed case with `case_closed`.

#### Scenario: A recording is attached
- **WHEN** the biller attaches a WAV, MP3, FLAC, or M4A recording to an open case
- **THEN** the case lists the call with its format and size

#### Scenario: Not a recording
- **WHEN** the biller attaches a file that is not WAV, MP3, FLAC, or M4A audio
- **THEN** the request is refused with unsupported_audio and nothing is stored

### Requirement: Transcription runs only in the after-hours window, alone
The worker SHALL start a queued job only while the local time is inside its profile's window
(`transcription_start_hour` to `transcription_end_hour`, default 19 to 7), one job at a time,
holding the `transcription` role through the memory guard. A job the guard keeps waiting
(`model_busy`) SHALL return to `queued`; any other failure SHALL end it `failed` with its error
code. A bad window setting SHALL read as the default window.

#### Scenario: Outside the window nothing runs
- **WHEN** a job is queued and the local time is outside the window
- **THEN** no model loads and the job stays queued

#### Scenario: Inside the window the call is transcribed
- **WHEN** a job is queued and the local time is inside the window
- **THEN** the call is transcribed by the transcription model and the job ends done

### Requirement: The reference number and rep instructions land in the case
A finished transcription SHALL be sealed into the case as a `transcript` item (audited
`call_transcribed`) with the transcript text, the reference number read from it, and the rep's
instructions read from it; the case SHALL show them with the call.

#### Scenario: The transcript's notes are shown with the case
- **WHEN** a call's transcription finishes
- **THEN** the case shows the call's reference number, the rep's instructions, and the transcript

### Requirement: Transcription state is PHI-free
The persisted job queue, logs, and errors SHALL hold only IDs, states, dates, and error codes,
never audio, transcript text, or filenames.

#### Scenario: The queue file holds no case content
- **WHEN** a call is queued and transcribed
- **THEN** the queue file and the logs hold no transcript text and no filename
