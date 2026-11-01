# Test Report: US-11.1 Transcribe Recorded Payer Calls After Hours

Change: us-11-1-payer-call-transcription
Story: US-11.1
Verdict: pass
Coverage: 1/1 acceptance criteria evaluated
Date: 2026-10-31
Tester: Claude Code (Opus 5.5), independent tester run
Environment: macOS 27.2 (Darwin 27.2.0, Apple M3 Pro); Python 3.12.9 (project `.venv`); Node 26.13.0; Hermes Agent v0.22.5; local time zone CST (UTC-6) during the run

## Acceptance Criteria Evaluated

| # | Criterion (quoted from SPECS.md) | Result | Evidence |
|---|---|---|---|
| 1 | "An attached call is queued for transcription: Then a transcription job is queued for the after-hours window" | PASS | `test_us_11_1_attached_call_queued`, `test_us_11_1_queued_inside_the_window_may_start_now`, `test_us_11_1_submitting_a_queued_call_again`, and `test_us_11_1_a_finished_call_is_queued_again` pass through the gateway. Pane (node): `test_us_11_1_pane_attached_call_queued` passes. Operator run on scratch case `case_3bfe5284bdb6ef37`: `make case-call` with a synthetic 3244-byte WAV returned `call_a8e88ac7535b09fa` (`format: wav`). At 19:44:52 local, with the profile window set to 2 to 5, `make case-transcribe` answered job `trj_a2018c62702323cf` with `"state": "queued"`, `window {start_hour: 2, end_hour: 5}`, and `not_before: 2026-11-01T08:00:00Z`, which is 02:00 local, the next start of the window. Submitting again returned the same `job_id`, and `make transcription-queue` listed one job. `make case-show` listed the call with its job `queued` and `transcript: null`. Two scheduler passes outside the window (19:45:27 and 19:46:27) loaded no model and sent no request to the stand-in transcription server. The job stayed `queued` with `started_at: null`. `queue.json` has mode 0600 and holds IDs, states, the window, dates, and an error code only |

## Evidence Commands

```bash
make evidence STORY=US-11.1
make test-story STORY=US-11.1
node --import ./plugin/desktop/tests/register-fakes.mjs --test plugin/desktop/tests/payer_calls.test.mjs
uv run pytest -m "not models" -p no:cacheprovider --no-cov -q \
  -k "test_us_7_3_no_transmitting_route or test_us_1_5_runbooks_have_sections or test_us_1_3"
# operator run against a scratch worker (serve_call_worker.py in the session scratchpad:
# real create_app, tests/fakes make_service with a FakeModelServer and InMemoryKeyProvider, a
# per-launch token from issue_token, configure_logging into a scratch worker.log, the real
# TranscriptionQueue and TranscriptionScheduler (60 s tick), and a stand-in pipeline provider whose
# transcription endpoint is a loopback fake mlx_audio server on 18215 that records request shape
# only and answers a synthetic transcript; a `busy` file makes the provider raise ModelBusyError)
export HERMES_HOME=<scratch>/hermes MODELS_HOME=<scratch>/models WORKER_PORT=18214
# <scratch>/hermes/config.yaml: transcription_start_hour: 2, transcription_end_hour: 5
make case-new
make case-call CASE=case_3bfe5284bdb6ef37 FILE="<scratch>/data/Jane Doe call 1970-01-01.wav"
make case-call CASE=case_3bfe5284bdb6ef37 FILE=<scratch>/data/notes.txt      # text
make case-call CASE=case_3bfe5284bdb6ef37 FILE=<scratch>/data/fake.wav       # HTML named .wav
make case-call CASE=case_3bfe5284bdb6ef37 FILE=<scratch>/data/big.wav        # 128 MiB + 1 byte
make case-call CASE=case_3bfe5284bdb6ef37 FILE=<scratch>/data/missing.wav; make case-call CASE=...
make case-show CASE=case_3bfe5284bdb6ef37
make case-transcribe CASE=case_3bfe5284bdb6ef37 CALL=call_a8e88ac7535b09fa   # twice
make transcription-queue
make case-transcribe CASE=case_3bfe5284bdb6ef37 CALL=call_0000000000000000
make case-transcribe CASE=case_3bfe5284bdb6ef37 CALL=bogus; make case-transcribe CASE=case_3bfe5284bdb6ef37
make case-transcribe CASE=case_0000000000000000 CALL=call_a8e88ac7535b09fa
make case-new; make case-call ...; make case-outcome OUTCOME=upheld          # second case, closed
make case-transcribe CASE=case_262ee1f2cec058dd CALL=call_38417b031b196b3a; make case-call ...
# wait past two scheduler ticks; then config.yaml start=end=9 (invalid -> default 19 to 7) + touch busy
# next tick: guard busy; then rm busy; next tick: transcribed
make transcription-queue; make case-show CASE=case_3bfe5284bdb6ef37
make case-transcribe CASE=case_3bfe5284bdb6ef37 CALL=call_a8e88ac7535b09fa   # after done
make corpus-audit CASE=case_3bfe5284bdb6ef37
curl ... "http://127.0.0.1:18214/corpus/audit?profile=default&case_id=case_3bfe5284bdb6ef37"
stat queue.json; grep for "Jane Doe", "SYNTH", "SYN-0001", "5501234", "resubmit", ".wav" in queue.json, worker.log, and the whole scratch store
kill -TERM <worker pid>; lsof -nP -iTCP:18214 -sTCP:LISTEN; lsof -nP -iTCP:18215 -sTCP:LISTEN
```

```text
$ make evidence STORY=US-11.1
tests/test_us_11_1_payer_calls.py ...................................... [ 46%]
............................................                             [100%]
- generated xml file: .../evidence/US-11.1/junit.xml -
===================== 82 passed, 1418 deselected in 3.52s ======================
junit.xml: tests=82 failures=0 errors=0 skipped=0 (43 test functions, parametrized)
  test_us_11_1_attached_call_queued, _queued_inside_the_window_may_start_now,
  _submitting_a_queued_call_again, _a_finished_call_is_queued_again, _recording_attached (5),
  _not_a_recording (6), _empty_recording, _recording_too_large, _unknown_call_and_closed_case,
  _outside_the_window_nothing_runs, _inside_the_window_the_call_is_transcribed,
  _transcript_notes_shown_with_the_case, _queue_file_holds_no_case_content,
  _busy_guard_queues_the_job_again, _failed_transcription (5),
  _closed_case_fails_before_the_model_loads, _case_closed_while_transcribing,
  _worker_lifespan_runs_the_scheduler, _window_contains (9), _window_settings (8),
  _notes_reference_number (12), _queue_running_jobs_are_queued_again_at_load, _purge_removes_calls, ...
junit-node.xml: 3 US-11.1 cases, fail 0
  test_us_11_1_pane_attached_call_queued
  test_us_11_1_pane_recording_refused
  test_us_11_1_pane_transcript_notes_shown

$ make test-story STORY=US-11.1
===================== 82 passed, 1418 deselected in 3.48s ======================
  ✔ test_us_11_1_pane_attached_call_queued / _pane_recording_refused / _pane_transcript_notes_shown
ℹ tests 12  ℹ pass 12  ℹ fail 0
payer_calls.test.mjs (whole file): ℹ tests 10  ℹ pass 10  ℹ fail 0
test_us_7_3_no_transmitting_route, test_us_1_5_runbooks_have_sections, test_us_1_3*: 41 passed

$ make case-call ... "Jane Doe call 1970-01-01.wav"
"call": {"call_id": "call_a8e88ac7535b09fa", "format": "wav", "filename": "Jane Doe call 1970-01-01.wav",
         "size_bytes": 3244, "added_at": "2026-11-01T01:44:44.647965Z"}               exit=0
$ make case-call ... notes.txt | fake.wav
curl: (22) The requested URL returned error: 415
    "error": {"code": "unsupported_audio", "message": "ClaimCoach accepts WAV, MP3, FLAC, and M4A call recordings only."}
$ make case-call ... big.wav (134217729 bytes)
curl: (22) The requested URL returned error: 413
    "error": {"code": "call_too_large", "message": "The call recording is larger than ClaimCoach accepts (128 MiB)."}
case-show afterwards: calls 1
$ make case-call ... missing.wav   |  no FILE
usage: make case-call CASE=<case id> FILE=<document>                                  exit=2

$ date; make case-transcribe CASE=case_3bfe5284bdb6ef37 CALL=call_a8e88ac7535b09fa
Sat Oct 31 19:44:52 CST 2026
"job": {"job_id": "trj_a2018c62702323cf", "profile": "default", "state": "queued",
        "window": {"start_hour": 2, "end_hour": 5},
        "queued_at": "2026-11-01T01:44:52.902311Z", "not_before": "2026-11-01T08:00:00Z",
        "started_at": null, "finished_at": null, "error_code": null}
(again) -> same job_id trj_a2018c62702323cf, state queued; make transcription-queue: 1 job
make case-show: calls[0].transcription.state "queued", calls[0].transcript null

call_0000000000000000           -> 404 "code": "call_not_found"  "No such call recording in this case."
CALL=bogus | no CALL            -> usage: make case-transcribe CASE=<case id> CALL=<call id from make case-call>  exit=2
case_0000000000000000           -> 404 "code": "case_not_found"
closed case_262ee1f2cec058dd    -> case-transcribe 409 "code": "case_closed"; case-call 409 "code": "case_closed"

19:46:45 (after the ticks at 19:45:27 and 19:46:27): no model loads, no transcription requests;
  job state "queued", started_at null

config.yaml start=end=9 + busy; tick 19:47:27:
  loads.log: transcription
  worker.log: "a profile's transcription window is invalid; the default window is used"
              "transcription waits for the memory guard; queued again"  job_id trj_a2018c62702323cf
  job state "queued", started_at null
busy removed; tick 19:48:27:
  loads.log: transcription (2nd)
  fake server saw: {"bytes": 3798, "sends_call_wav": true, "has_biller_filename": false, "has_riff": true}
  worker.log: "transcription done"  job_id trj_a2018c62702323cf
  job state "done", started_at 01:48:27.358329Z, finished_at 01:48:27.382282Z, error_code null

$ make case-show CASE=case_3bfe5284bdb6ef37
"transcript": {"call_id": "call_a8e88ac7535b09fa", "text": "Thank you for calling SYNTH payer. ...",
  "reference_number": "5501234",
  "rep_instructions": ["You need to resubmit it as a corrected claim with the authorization number attached.",
                       "Please fax the medical records to the appeals unit within 30 days."],
  "transcribed_at": "2026-11-01T01:48:27.381759Z"}       closed_at None
$ make case-transcribe ... (after done) -> new job trj_c5ebc0e9e0a8c12d, queued, not_before now; queue holds 1 job;
  next tick -> done

$ make corpus-audit CASE=case_3bfe5284bdb6ef37
error: worker_unavailable          (expected against this harness; see Notes)
GET /corpus/audit: seq 1 case_created | 2 call_added | 3,4,9 case_opened | 10 call_transcribed 01:48:27.381982Z
                   11 case_opened | 12 call_transcribed 01:49:27.403529Z   ({seq, at, action, case_id, profile} only)

$ stat queue.json
-rw------- .../transcription/queue.json       drwx------ .../transcription
job keys: call_id case_id error_code finished_at job_id not_before profile queued_at started_at state window
"Jane Doe" | "SYNTH" | "SYN-0001" | "5501234" | "resubmit" | ".wav":
  queue.json 0, worker.log 0, plaintext files under the scratch Hermes root 0 (each)
after SIGTERM: ports 18214 and 18215 free; no harness process left
```

Artifacts: `evidence/US-11.1/junit.xml`, `evidence/US-11.1/junit-node.xml`

## Failures

None.

## Notes

- SPECS.md still marks US-11.1 `NEEDS CLARIFICATION`, with open questions on the window, the
  formats, and how the notes are shown. The change answers them: a per-profile window (default 19
  to 7), WAV, MP3, FLAC, or M4A up to 128 MiB, and a reference number plus rep instructions shown
  with the call. I tested against those answers.
- Spec-delta scenarios (`openspec/changes/us-11-1-payer-call-transcription/specs/payer-call-transcription/spec.md`):
  - "An attached call is queued for transcription" (adds: AND the case shows the call with its
    job in state queued). PASS. The evidence is row 1, including `make case-show` showing
    `transcription.state: queued`.
  - "Submitting a queued call again": the same job is answered and no second job is queued.
    PASS. `test_us_11_1_submitting_a_queued_call_again`. Operator: the same `job_id` came back,
    and the queue held one job. After `done`, submitting again replaced the job with a new one
    (`test_us_11_1_a_finished_call_is_queued_again`), as the requirement says.
  - "A recording is attached": the case lists the call with its format and size. PASS.
    `test_us_11_1_recording_attached` covers WAV, MP3 (ID3 and frame sync), FLAC, and M4A.
    Pane: `test_us_11_1_pane_attached_call_queued`. Operator: WAV only. `make case-show` listed
    `format: wav` and `size_bytes: 3244`, and the audit has `call_added`. MP3, FLAC, and M4A
    were checked only by the tests.
  - "Not a recording": refused with `unsupported_audio`, and nothing is stored. PASS.
    `test_us_11_1_not_a_recording` (6 cases), `test_us_11_1_empty_recording`, and
    `test_us_11_1_recording_too_large`. Pane: `test_us_11_1_pane_recording_refused`. Operator: a
    text file and an HTML file named `.wav` both got `415 unsupported_audio`. A 128 MiB + 1 byte
    file got `413 call_too_large`. The case still listed one call. A closed case got
    `409 case_closed` both for attaching and for queuing.
  - "Outside the window nothing runs": no model loads, and the job stays queued. PASS.
    `test_us_11_1_outside_the_window_nothing_runs`. Operator: in two real scheduler passes
    outside the 2-to-5 window, the provider recorded no load and the fake server got no request.
  - "Inside the window the call is transcribed": the transcription model transcribes the call,
    and the job ends done. PASS against a stand-in server only.
    `test_us_11_1_inside_the_window_the_call_is_transcribed`. Operator: the real scheduler took
    the `transcription` role and posted the recording to the fake `/v1/audio/transcriptions`.
    It sent the recording under the fixed name `call.wav`, without the biller's filename. The
    job ended `done`. A real Voxtral-Small-24B transcription was **UNVERIFIED**, because no
    model weights were used (out of scope). `make test-models` was not run. Also not exercised:
    the `ModelManager` memory guard itself (the stand-in provider raised `ModelBusyError`, and
    the requeue path did run), M4A through `ffmpeg`, and the `mlx_audio` server.
  - "The transcript's notes are shown with the case": the case shows the reference number, the
    rep's instructions, and the transcript. PASS. `test_us_11_1_transcript_notes_shown_with_the_case`
    and the pane's `test_us_11_1_pane_transcript_notes_shown`. Operator: `make case-show` showed
    `reference_number: "5501234"`, read from the spoken "5 5 0 1 2 3 4". It showed the two
    instruction sentences and the full text, and the audit has `call_transcribed`. The notes
    were read from a synthetic transcript, not from real call audio.
  - "The queue file holds no case content": the queue file and the logs hold no transcript text
    and no filename. PASS. `test_us_11_1_queue_file_holds_no_case_content`. Operator:
    `queue.json` (0600, in a 0700 folder) has only the keys listed above. Grepping `queue.json`,
    `worker.log`, and every file under the scratch Hermes root for the filename, the synthetic
    transcript markers, the reference number, and `.wav` found 0 matches. The worker log lines
    hold job IDs, states, and fixed messages only.
- The window is read live on every tick, and the job's stored `window` and `not_before` are not
  updated. After I moved the window from 2-5 to an invalid value (which reads as the default
  19-7), the job queued with `window 2-5, not_before 08:00Z` ran at 01:48Z. That matches the
  spec ("the profile's window") and the runbook ("the next tick reads them"). But the done job
  still shows `window {2, 5}` and a `not_before` later than its `started_at`. So the runbook's
  check "started_at and finished_at inside the window" holds only against the profile's current
  window, not against the window printed on the job. This is an observation, not a failure of
  a stated criterion. The settings warning "transcription window is invalid" is also logged on
  every tick and on every queue request while the setting is bad.
- The `make case-call` usage line for a missing or absent FILE reads `FILE=<document>`, from the
  shared `REQUIRE_CASE_FILE`, not `FILE=<recording>`. This is cosmetic. `make` still exits 2
  without calling the worker.
- How the operator run was isolated: `serve_call_worker.py` in this tester's scratchpad
  (`.../scratchpad/tester-11-1/`), not in the repo. It ran the real `create_app`, with
  `HERMES_HOME` and `MODELS_HOME` set to scratch folders (the script refuses any other path), an
  `InMemoryKeyProvider` (no Keychain item), and an in-process `FakeModelServer` for the corpus. It
  served on 127.0.0.1:18214 with `WORKER_PORT=18214`, and the fake transcription server ran on
  127.0.0.1:18215. All data was synthetic: a 0.1 s silent PCM WAV, plus a PHI-like filename used
  as a leak canary. The worker was stopped with SIGTERM, and both ports were free afterwards. No
  model was downloaded or loaded, and the real `~/.hermes` and any real worker were not touched.
- `make corpus-audit` printed `error: worker_unavailable` against this harness. This is expected,
  as in US-7.1 and US-8.1: the corpus CLI sends the token only to a worker that the launcher
  recorded in its PID file. I read the same audit through `GET /corpus/audit` with curl instead.
- Not exercised in the operator run, tests only: a job left `running` by a stopped worker being
  queued again at start (`test_us_11_1_queue_running_jobs_are_queued_again_at_load`), failure
  codes (`test_us_11_1_failed_transcription`), a case closed before or during a run, and the
  retention purge of calls (`test_us_11_1_purge_removes_calls`). The **Payer calls** pane was
  rendered only under `register-fakes.mjs`. It was not seen in a live Hermes desktop, so the
  live pane is UNVERIFIED.

## Re-verification after the review fixes

The independent review (`openspec/changes/us-11-1-payer-call-transcription/review.md`) found that
the real `mlx_audio.server` (mlx-audio 0.5.8) differs from the stand-in this run used. The fixes
changed the server command, the upload name, the response format, and the scheduler's window
bounds, so the Python suite was recorded again by the implementer, not by the tester:

```bash
make evidence STORY=US-11.1
make check
```

```text
===================== 96 passed, 1419 deselected in 2.81s ======================
TOTAL    6995      0   1172      0   100%
=============== 1505 passed, 10 deselected in 177.41s (0:02:57) ================
ℹ all files   | 100.00 |   100.00 |  100.00 |
```

`junit.xml` now holds 96 tests (the 82 above plus 14 review regressions); `junit-node.xml` holds
the US-11.1-named pane tests. The operator run above predates the fixes; its observations 1
(stale window on a queued job) and 3 (`FILE=<document>`) are fixed. A real Voxtral transcription
stays **UNVERIFIED**: `test_us_11_1_real_voxtral_transcribes_a_spoken_call`
(`@pytest.mark.models`, speech from macOS `say`) skips because
`~/Models/Voxtral-Small-24B-2507-4bit` is not downloaded, and the `mlx-vlm` venv's
`mlx_audio.server` does not import until `webrtcvad` is installed.
