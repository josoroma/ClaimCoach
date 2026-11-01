# Design: US-11.1 transcribe recorded payer calls after hours

## Context

The `transcription` role (`mlx-community/Voxtral-Small-24B-2507-4bit`, `mlx_audio.server`, port
18207, `tier_b: 24`, `runs_alone: true`) is in `models.default.yaml` since US-2.1, and US-2.3's
memory guard starts it only when no other server is resident and queues every other load while it
is. Cases store sealed items in the profile's user scope (US-5.1). Case jobs (`JobRegistry`, US-5.2)
live in memory and run at once; a transcription must wait for a window that may be hours away and
survive a worker restart. SPECS.md leaves three questions open; each is decided below.

## Goals / Non-Goals

Goals: attach a call recording to a case; queue it for the after-hours window; transcribe it
there with the local Voxtral server; store the transcript, the reference number, and the rep's
instructions with the case; show them in the pane.

Non-Goals: live or streaming transcription; speaker diarization; writing the reference number
into the extraction's fields or the appeal draft; agent access to transcripts (the US-9.2 summary
is unchanged); a "transcribe now" override.

## Decisions

1. **"After hours" is a user-configured local window, default 19:00-07:00 (open question 1).**
   Two integer settings, `transcription_start_hour` and `transcription_end_hour` (0-23, local time,
   the window wraps midnight). A job starts only inside its profile's window, and only one at a
   time. Equal hours, out-of-range, or unreadable values fall back to the default window, which is
   after hours, so a bad setting can never move Voxtral into the working day. The scheduler checks
   every minute, and re-checks the window before each job. A call starts only with at least 45
   minutes of window left (`MIN_WINDOW_LEFT`), and its request is stopped 15 minutes after the
   window closes (`WINDOW_GRACE`, `processing_timeout`), so Voxtral never holds the morning
   hostage. A queued job is shown under the profile's current window; a started one records the
   window it ran in. Rejected: idle detection (macOS idle time says
   nothing about whether the biller needs a model in a minute, and a 24B load takes minutes to
   undo); a fixed window (practices keep different hours).
2. **Voxtral is loaded only through the memory guard; a busy guard re-queues the job.** The job
   holds `models.use("transcription")`, so `runs_alone` evicts idle servers and queues behind busy
   ones. If the guard keeps the load queued past `queue_timeout_s` (`model_busy`), the job goes back
   to `queued` and is tried on the next tick; any other failure ends it `failed` with its code. The
   idle sweep unloads Voxtral afterwards, and a morning load evicts it when idle. Rejected:
   stopping the biller's servers (would drop work in progress).
3. **Accepted formats: WAV, MP3, FLAC, M4A, sniffed from the bytes (open question 2).** These are
   what call recorders and Voice Memos produce, and what `mlx_audio.audio_io.read` decodes in
   memory (WAV, MP3, FLAC through miniaudio; M4A through ffmpeg). The kind comes from the leading
   bytes (`RIFF....WAVE`, `ID3` or an MPEG frame sync, `fLaC`, `....ftyp` with an M4A/MP4 brand),
   never the filename. Every format is uploaded to the server as `call.wav`: the server decodes the
   bytes, then writes them to a temporary file under the upload's suffix, and it cannot write M4A.
   Limit 128 MiB: an hour of 16 kHz 16-bit mono WAV is about 115 MiB; Voxtral transcribes about 30
   minutes in one pass (decision 7). Rejected: Ogg/Opus/WebM (rare from call recorders; add
   when asked); converting audio in the worker (a new dependency for no gain).
4. **The reference number and rep instructions are read from the transcript by fixed rules, and
   shown for the biller to check (open question 3).** `notes.reference_number` takes the last
   reference/confirmation/ticket number spoken (reps repeat it at the end; earlier mentions are
   often a previous call's), joining spoken digit groups, 4-32 characters with at least one digit.
   `notes.rep_instructions` keeps, in order and without repeats, up to ten statements (not
   questions) that hold an instruction cue ("you need to", "please", "resubmit", "fax", "attach",
   "within 30 days", "corrected claim", ...). The pane shows both under the call with "check
   against the transcript", and the full transcript below. Rejected: a second model pass to
   extract them (another model load in the night, behind a 24B model that runs alone, and output
   that is not repeatable); copying them into the extraction's fields (they are not EOB fields and
   would make the diagnosis stale).
5. **The queue is a small PHI-free JSON file, the transcript a sealed case item.** `TranscriptionJob`
   holds the profile name, case and call IDs, a state (`queued`, `running`, `done`, `failed`),
   dates, and an error code: nothing a recording or transcript says. It is written atomically with
   mode 0600 under `<hermes root>/plugin-data/claimcoach/transcription/`. A job found `running` at
   load (the worker stopped mid-call) is queued again. Finished jobs are kept 30 days, then
   dropped. The recording (`call`) and the transcript (`transcript`) are sealed case items, so the
   US-4.5 purge removes both with the case. Rejected: keeping job state in the call item (a status
   update would rewrite the sealed recording); an in-memory queue (a restart would lose the night's
   work).
6. **Queuing is idempotent per call.** Submitting a call with a queued or running job returns that
   job; submitting one that is done or failed queues it again (the new transcript replaces the
   old). The answer names the window and `not_before`, the window's next start (now, inside it).
   A closed case refuses new recordings and new jobs (`case_closed`); a job whose case closed while
   it waited ends `failed` with `case_closed` before any model loads.

7. **A transcript cut off at the length limit is flagged, not failed.** Voxtral generates the
   whole transcript in one pass under `max_tokens` (8192, about 30 minutes of speech). The request
   asks for `verbose_json`, whose `generation_tokens` reaching the limit sets
   `CallTranscript.truncated`; the pane says the end of the call (where the reference number is
   often repeated) is missing. Rejected: splitting audio in the worker (needs an audio decoder
   dependency for every format); failing the job (the first 30 minutes are still useful).
8. **The server command matches `mlx_audio.server`.** It has no `--model` flag (it loads the model
   each request names), so the default command drops it and gains `--log-dir {logs}`, a new
   placeholder for a 0700 folder in the worker's data dir; an unedited older copy of
   `models.yaml` is migrated once, as US-7.1 did. Every model server now starts with umask 077.

## Risks / Trade-offs

- [M4A needs ffmpeg in the model server's environment] → the runbook says so; a missing ffmpeg
  fails the job with `model_unavailable`, and the biller can attach WAV or MP3 instead.
- [`mlx_audio.server` writes the decoded call, unencrypted, to `/tmp/<time>_<id>.wav` while it
  transcribes, and removes it afterwards; a server killed mid-call leaves it] → the server starts
  with umask 077, so the file is owner-only; nothing leaves the Mac (BR-1); the runbook's Rollback
  says how to find and remove a leftover after a crash. ClaimCoach does not sweep `/tmp` itself:
  other mlx-audio apps on the Mac use the same file names.
- [mlx-audio 0.5.8 imports `webrtcvad`, which the `mlx-vlm` venv may lack] → the runbook's
  Preconditions check that `mlx_audio.server` imports; until it does every job ends
  `model_unavailable`.
- [An invalid window setting is logged on every pass while it stays invalid] → accepted: the
  warning is the operator's cue to fix it, and the default window applies meanwhile.
- [Rule-based notes miss a reference number said in words ("A as in apple")] → the transcript is
  always shown in full, and the notes are labeled for checking.
- [The window uses the Mac's local time; on a DST change night the next start can be an hour
  off] → the scheduler re-checks `contains` every minute, so a job never runs outside the window.
- [128 MiB bodies are held in memory in the gateway and the worker] → bounded by
  `read_limited`, one upload at a time per request; the same pattern as US-5.1 at a larger bound.
