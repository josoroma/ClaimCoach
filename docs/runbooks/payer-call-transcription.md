# Runbook: payer-call transcription

Covers US-11.1 (v1.1): the biller attaches a recorded payer call to a case and queues it; the
worker transcribes it in the profile's after-hours window with the local Voxtral server
(`transcription` role, `Voxtral-Small-24B-2507` 4-bit, port 18207), alone, and the case then shows
the call's reference number, the rep's instructions, and the transcript. Billers do this in the
ClaimCoach pane: the **Payer calls** section, **Attach a call recording**, then **Transcribe after
hours**. These commands are for operators checking the worker by hand. Every command talks to the
worker on `127.0.0.1` only (BR-1, BR-2).

The recording and the transcript are sealed into the case like its documents (BR-6, BR-13) and
are purged with it (BR-7). The queue file
`<hermes root>/plugin-data/claimcoach/transcription/queue.json` (mode 0600) holds IDs, states,
windows, dates, and error codes only (BR-14). `make case-call` and `make case-show` print the
recording's filename, and `make case-show` prints the transcript, to your terminal; do not paste
their output into tickets, chats, or the agent transcript.

## Preconditions

- The worker is running: `make start` (see [worker-start-stop-health](worker-start-stop-health.md)).
- The transcription model is present: `make models-check` lists `transcription` with its weights;
  otherwise `make models-download ROLE=transcription CONFIRM=yes` (see
  [model-download-convert](model-download-convert.md)). The `mlx-vlm` venv's `mlx_audio.server`
  imports (mlx-audio 0.5.8 also needs `webrtcvad`):

  ```bash
  "$MODELS_HOME/.venvs/mlx-vlm/bin/python" -c "import mlx_audio.server" && echo ok
  ```

- `models.yaml` in the data dir has the current `transcription` command (no `--model`; ends with
  `"--log-dir", "{logs}"`). An unedited older copy is migrated when the worker starts; an edited
  one must be changed by hand in `$HERMES_HOME/plugin-data/claimcoach/models.yaml`.
- `ffmpeg` is on the model server's `PATH` (`which ffmpeg`): the server decodes M4A with it and
  re-encodes every call through it. Calls longer than about 30 minutes are transcribed up to
  that point and flagged as cut off.
- The case is open (`make case-show CASE=<id>` answers it with `"closed_at": null`).
- The window suits the practice. Each profile sets it in Settings → Plugins → ClaimCoach, stored
  in that profile's `config.yaml` (local hours, 0-23; the window wraps midnight):

  ```yaml
  plugins:
    entries:
      claimcoach:
        settings:
          transcription_start_hour: 19
          transcription_end_hour: 7
  ```

  Equal, out-of-range, or unreadable values read as the default, 19 to 7. Voxtral runs alone: while
  it transcribes, every other model load waits, so keep the window outside working hours.

## Steps

1. Attach a recording (WAV, MP3, FLAC, or M4A, up to 128 MiB) and note its `call_id`:

   ```bash
   make case-call CASE=case_0123456789abcdef FILE=payer-call.wav
   ```

2. Queue it for the after-hours window:

   ```bash
   make case-transcribe CASE=case_0123456789abcdef CALL=call_0123456789abcdef
   ```

   The answer is the job: `"state": "queued"`, the `window`, and `not_before`, when it may start
   (now, inside the window). Running it again returns the same job.

3. Watch the queue (no case content):

   ```bash
   make transcription-queue
   ```

   Inside the window the worker starts queued calls one at a time while at least 45 minutes of
   the window are left: `running`, then `done` or `failed` with an `error_code`. A queued job is
   shown under the profile's current window; a started one keeps the window it ran in.

## Verification

- `make transcription-queue` shows the job `done`, with `started_at` inside the window it shows
  and `finished_at` at most 15 minutes after that window's end.
- `make case-show CASE=case_0123456789abcdef` shows the call under `calls` with
  `transcript.reference_number`, `transcript.rep_instructions`, and `transcript.text`; the pane
  shows the same under **Payer calls**, labeled for checking against the transcript.
- `make corpus-audit CASE=case_0123456789abcdef` lists `call_added` and `call_transcribed`.
- `worker.log` has `transcription done` under the job's ID and no filename or transcript text.
- A job `failed` with `model_unavailable`: the weights or `mlx_audio` (or `ffmpeg`, for M4A) are
  missing; fix the precondition and queue the call again (step 2). `case_closed`: the case closed
  before the call ran; nothing was loaded. A job back in `queued` after its window opened: the
  memory guard kept Voxtral waiting for a busy model; it is tried again a minute later.
  `processing_timeout`: the call was still running 15 minutes after the window closed; queue it
  again. A transcript marked `"truncated": true` stops about 30 minutes into the call.

## Rollback

- A queued job cannot be cancelled on its own; record the case's outcome or let it run. To stop
  all transcription now, stop the worker (`make stop`): a running job is queued again at the next
  start.
- To take a recording and its transcript out of a case before retention, purge the case with an
  approved request (see [phi-purge](phi-purge.md)).
- To move transcription out of a night, change the two settings; the next tick reads them.
- Voxtral is unloaded by the idle sweep after `idle_timeout_s`, or at once with
  `make models-unload ROLE=transcription`.
- After a crash or a forced stop during a transcription, look for the server's decoded call and
  remove it (owner-only, your user):

  ```bash
  find /tmp/ -maxdepth 1 -user "$USER" -name '*_*.wav' -mmin -300 -print
  ```
