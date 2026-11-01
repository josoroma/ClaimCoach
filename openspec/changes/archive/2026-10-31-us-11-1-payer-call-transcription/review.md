# Review: US-11.1

Change: us-11-1-payer-call-transcription
Reviewer: independent `story-reviewer` agent (read-only, given the change name and changed files, not the implementer's reasoning), 2026-10-31, checked against the installed mlx-audio 0.5.8 source; independent `story-tester` operator run on a scratch worker
Verdict: pass after fixes (a real Voxtral transcription stays UNVERIFIED until the weights and `webrtcvad` are installed)

## Findings and resolution

| Severity | Finding | Resolution |
|---|---|---|
| high | The registry's `transcription` command (since US-2.1) passes `--model`, which `mlx_audio.server` does not have, so the server exits 2 and every job ends `model_unavailable`; the venv also lacks `webrtcvad`, which mlx-audio 0.5.8 imports | The default command drops `--model` (the request names the model) and gains `--log-dir {logs}`; an unedited older `models.yaml` copy is migrated once (`_migrate_commands`, shared with US-7.1). The runbook's Preconditions check that `mlx_audio.server` imports; the upgrade runbook has the row. Design decision 8; `test_us_11_1_unedited_transcription_command_migrates`, `test_us_2_1_paths_resolve_under_models_home` (updated). `webrtcvad` is an operator install (not done here) |
| high | M4A always failed: the upload's suffix becomes the server's temp-file suffix, and it cannot write `.m4a`; the runbook wrongly said WAV/MP3/FLAC are decoded in memory | Every format is uploaded as `call.wav` (the server decodes by bytes). Design decision 3 and Risks corrected; `test_us_11_1_every_format_is_sent_as_call_wav` |
| medium | `max_tokens` caps the whole transcript; a long call was cut off silently and its final reference number lost | `verbose_json` is requested; `generation_tokens` reaching `MAX_TOKENS` sets `CallTranscript.truncated`, and the pane warns that the end of the call is missing. Design decision 7; `test_us_11_1_a_transcript_cut_off_at_the_limit_is_flagged`, node "a transcript cut off at the length limit says so" |
| medium | The server writes the decoded call unencrypted to `/tmp`, under the inherited umask, and leaves it if killed | Every model server starts with `umask=0o077` and a 0700 `{logs}` folder in the data dir; the design's Risks and the runbook's Rollback name the leftover file. ClaimCoach does not sweep `/tmp` (other mlx-audio apps on the Mac use the same names). `test_us_11_1_model_servers_spawn_owner_only_with_a_logs_folder` |
| medium | The window only gated a job's start; a call started at 06:59 held Voxtral alone into the morning for up to 4 h | A call starts only with 45 minutes of window left (`MIN_WINDOW_LEFT`), and its request deadline is the window's end plus 15 minutes (`WINDOW_GRACE`), ending `processing_timeout` (`TranscriptionTimeoutError`). `test_us_11_1_no_call_starts_near_the_window_end`, `test_us_11_1_a_call_is_stopped_after_the_window_ends`, `test_us_11_1_window_remaining` |
| low | Queue memory changed before the file was written; a failed write left a job `running` in memory | `_commit` writes first and swaps memory only after; `test_us_11_1_queue_write_failure_leaves_the_old_file` (extended) |
| low | Views showed a queued job's window as stored at queue time, not the one the scheduler uses (also tester observation 1) | Queued jobs are shown under the profile's current window and `not_before`; `start()` records the window a job ran in. `test_us_11_1_views_show_the_current_window` |
| low | After the 30-day prune, a transcribed call read "Not transcribed yet." | The pane reads a call with a transcript and no job as transcribed; node "a call whose finished job was forgotten still reads as transcribed" |
| low | `mlx_audio.server` creates `logs/` in its working directory, possibly the install dir | `--log-dir {logs}` (finding 1's fix) |
| low | Reference cues matched inside words (`REFUND`) and `case`/`tracking` replaced the real number under "last wins" | Cue words end on a word boundary; `case` and `tracking` are no longer cues. `test_us_11_1_notes_cues_are_whole_words` |
| nit (tester) | `make case-call` usage said `FILE=<document>` | Says `FILE=<recording>`; checked by hand |
| nit (tester) | An invalid window setting is warned on every pass | Accepted and recorded in the design's Risks |

Also checked by the reviewer and found sound: window wrap-around and the invalid-setting fallback; the queue's atomic 0600 writes, one job per call, running→queued at load, the 30-day prune, per-profile `due()` with skip; the scheduler's busy re-queue, failure codes, the case check before the model loads, closing mid-run, the loop surviving a bad pass, and cancellation before the stores close; loopback httpx with `trust_env=False`; no exception text or filenames in logs, responses, or the queue (BR-14); the `case_items` migration, purge, and audit actions; typed routes with fixed envelopes and bounded 128 MiB reads; the US-7.3 and US-1.3 route pins and the HTTP-client allow-list; the pane's defensive parsing and disabled controls.

## Re-verification

```text
$ make check
All checks passed!
TOTAL    6995      0   1172      0   100%
=============== 1505 passed, 10 deselected in 177.41s (0:02:57) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
$ make evidence STORY=US-11.1
===================== 96 passed, 1419 deselected in 2.81s ======================
$ make evidence-check
ok   US-11.1
```

`make verify` runs once for the four changes delivered together (EPIC-10 and EPIC-11); its result
is recorded in the US-10.3 review.
