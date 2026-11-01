# Proposal: US-11.1 Transcribe Recorded Payer Calls After Hours

## Why

PRD §6 story 8 (v1.1): the biller attaches a recorded payer call; ClaimCoach transcribes it after
hours and adds the reference number and the rep's instructions to the case. PRD §8 names the model
(`Voxtral-Small-24B-2507` 4-bit, `mlx_audio.server`, batch, run alone). US-2.1 to US-2.3 already
registered the `transcription` role on port 18207 with `runs_alone: true`, and the memory guard
already keeps it alone; nothing attaches, queues, or transcribes a call yet.

## What Changes

- New `claimcoach.calls` package:
  - `types.py`: typed `CallRecording`, `CallTranscript`, `TranscriptionJob`, `PayerCall`,
    `CallAdded`, `TranscriptionQueued`; audio limits.
  - `audio.py`: `sniff_audio` decides WAV, MP3, FLAC, or M4A from the bytes.
  - `window.py`: `TranscriptionWindow` (local start and end hour, wraps midnight), `contains`
    and `next_start`.
  - `queue.py`: `TranscriptionQueue`, the persisted, PHI-free job list (IDs, a state, dates, an
    error code) under `<hermes root>/plugin-data/claimcoach/transcription/queue.json`.
  - `transcribe.py`: the `POST /v1/audio/transcriptions` call to the loopback Voxtral server.
  - `notes.py`: the reference number and the rep's instructions, read from the transcript.
  - `scheduler.py`: `TranscriptionScheduler`, the worker's after-hours runner.
- Case items gain kinds `call` (the sealed recording) and `transcript`; audit actions
  `call_added` and `call_transcribed`; the retention purge counts recordings as documents.
- `Case` carries `calls: list[PayerCall]` (recording, its transcription job, its transcript).
- Worker routes `POST /cases/{case_id}/calls` (raw single-file multipart, up to 128 MiB) and
  `POST /cases/{case_id}/calls/{call_id}/transcribe`; matching gateway routes and
  `WorkerClient.upload_call` / `queue_transcription`.
- Settings `transcription_start_hour` (default 19) and `transcription_end_hour` (default 7);
  `load_transcription_window(home)`.
- Error codes `unsupported_audio`, `call_too_large`, `call_not_found`, `transcription_failed`.
- Pane: a Payer calls section to attach a recording, queue it, and read its status, reference
  number, rep instructions, and transcript.
- `make case-call`, `make case-transcribe`, `make transcription-queue`; the
  `payer-call-transcription` runbook.

## Capabilities

### New Capabilities
- `payer-call-transcription`: attaching a recorded payer call to a case, queuing it for the
  after-hours window, transcribing it with the local Voxtral server, and showing the reference
  number and rep instructions with the case.

### Modified Capabilities
- None (`no-send-submit`'s pinned route tables gain the two call routes; the requirement is
  unchanged).

## Impact

- `case_items`' CHECK gains two kinds; `_migrate_case_items` rebuilds older tables on open.
- Plugin settings gain two integers (`plugin.yaml` `config_schema` is regenerated).
- No new dependency: the transcription request is plain `httpx` multipart.
