# Tasks

## 1. Types, audio, window, notes

- [x] 1.1 `calls/types.py` (`CallRecording`, `CallTranscript`, `TranscriptionJob`, `PayerCall`, `CallAdded`, `TranscriptionQueued`), `calls/audio.py` `sniff_audio`; verify `test_us_11_1_recording_attached`, `test_us_11_1_not_a_recording`
- [x] 1.2 `calls/window.py` `TranscriptionWindow` and settings `transcription_start_hour` / `transcription_end_hour`, `load_transcription_window`; verify `test_us_11_1_window_*`, `test_us_1_1_*` (manifest drift)
- [x] 1.3 `calls/notes.py` reference number and rep instructions; verify `test_us_11_1_notes_*`

## 2. Store, queue, service

- [x] 2.1 Case item kinds `call` and `transcript`, audit actions `call_added` and `call_transcribed`, purge counts recordings; verify `test_us_11_1_recording_attached`, `test_us_11_1_purge_removes_calls`
- [x] 2.2 `calls/queue.py` `TranscriptionQueue` (atomic 0600 file, idempotent per call, running → queued at load, 30-day prune); verify `test_us_11_1_attached_call_queued`, `test_us_11_1_submitting_a_queued_call_again`, `test_us_11_1_queue_*`
- [x] 2.3 `CaseService.add_call`, `call_audio`, `save_transcript`, `Case.calls`; verify `test_us_11_1_transcript_notes_shown_with_the_case`

## 3. Transcription and scheduler

- [x] 3.1 `calls/transcribe.py` against `POST /v1/audio/transcriptions`; verify `test_us_11_1_transcribe_*`
- [x] 3.2 `calls/scheduler.py` `TranscriptionScheduler` mounted in the worker lifespan; verify `test_us_11_1_outside_the_window_nothing_runs`, `test_us_11_1_inside_the_window_the_call_is_transcribed`, `test_us_11_1_scheduler_*`

## 4. Routes and pane

- [x] 4.1 Worker and gateway routes, `WorkerClient.upload_call` / `queue_transcription`, error codes, route pins; verify `test_us_11_1_*` through the gateway, `test_us_7_3_no_transmitting_route`
- [x] 4.2 Pane Payer calls section; verify `node --test` `payer_calls.test.mjs`

## 5. Operations and evidence

- [x] 5.1 `make case-call`, `make case-transcribe`, `make transcription-queue`; `payer-call-transcription` runbook; verify `test_us_1_5_runbooks_have_sections`, story-tester operator run
- [x] 5.2 Record `evidence/US-11.1/test-report.md` and `junit.xml`; verify `make evidence-check`

## R. Independent review

- [x] R.1 Fix every finding in `review.md` with a regression test; verify `make verify`
