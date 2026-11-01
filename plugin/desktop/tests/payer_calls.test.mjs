/**
 * node --test suite for payer calls in the pane. US-11.1 scenarios:
 *   - An attached call is queued for transcription
 *   - A recording is attached / Not a recording
 *   - The transcript's notes are shown with the case
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import {
  addCall,
  CallsPanel,
  CasePane,
  callsOf,
  createCaseApi,
  describeCall,
  MAX_CALL_BYTES,
  openCase,
  queueTranscription,
  REFUSALS,
} from '../plugin.js';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const CASE = 'case_0123456789abcdef';
const CALL = 'call_0123456789abcdef';
const WINDOW = { start_hour: 19, end_hour: 7 };
const at = { calls: 20 };
const recording = {
  name: 'Payer call.wav',
  type: 'audio/wav',
  arrayBuffer: async () => new TextEncoder().encode('RIFF....WAVE').buffer,
};
const TRANSCRIPT = {
  call_id: CALL,
  text: 'You need to resubmit. Your reference number is 8417293.',
  reference_number: '8417293',
  rep_instructions: ['You need to resubmit.'],
  transcribed_at: '2026-11-01T02:00:00Z',
};

/** A job as the worker answers it. */
const job = (state, extra = {}) => ({
  job_id: 'trj_0123456789abcdef',
  profile: 'default',
  case_id: CASE,
  call_id: CALL,
  state,
  window: WINDOW,
  queued_at: '2026-10-31T10:00:00Z',
  not_before: '2026-10-31T19:00:00Z',
  started_at: null,
  finished_at: null,
  error_code: null,
  ...extra,
});

/** A case body as `GET /cases/{id}` returns it. */
function caseBody(calls = []) {
  return {
    ok: true,
    case_id: CASE,
    opened_at: '2026-10-30T10:00:00Z',
    closed_at: null,
    documents: [],
    extraction: null,
    calls,
  };
}

const call = (transcription = null, transcript = null) => ({
  recording: {
    call_id: CALL,
    format: 'wav',
    filename: 'Payer call.wav',
    content_type: 'audio/wav',
    size_bytes: 12,
    added_at: '2026-10-31T10:00:00Z',
  },
  transcription,
  transcript,
});

const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

/** A worker that keeps one case's calls, as plugin_api does. */
function backend() {
  const state = { calls: [], requests: [] };
  const rest = async (path, opts) => {
    state.requests.push({ path, method: opts?.method ?? 'GET', opts });
    if (path === `/cases/${CASE}/calls`) {
      state.calls = [call()];
      return { ok: true, case_id: CASE, call: state.calls[0].recording };
    }
    if (path === `/cases/${CASE}/calls/${CALL}/transcribe`) {
      state.calls = [call(job('queued'))];
      return { ok: true, case_id: CASE, job: job('queued') };
    }
    return caseBody(state.calls);
  };
  return { rest, state };
}

const life = (caseId = CASE) => ({
  live: true,
  action: 0,
  caseId,
  processing: null,
  onProgress() {},
});

function rerender(element, ...seed) {
  resetHooks();
  hooks.seed = seed;
  return element.type(element.props);
}

const panelOf = (pane) => {
  const element = pane.props.children[at.calls];
  return element.type(element.props);
};
const tick = () => new Promise((resolve) => setImmediate(resolve));
const latest = () => hooks.states[0].updates.at(-1);
const listOf = (panel) => panel.props.children[2];
const itemOf = (panel) => listOf(panel).props.children[0].props.children;

afterEach(() => runCleanups());

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-11.1 an attached call is queued for transcription', () => {
  test('test_us_11_1_pane_attached_call_queued', async () => {
    const { rest, state } = backend();
    const pane = { type: CasePane, props: { rest } };
    const ready = await openCase(createCaseApi(rest), CASE);
    assert.equal(ready.calls, undefined, 'a case without calls lists none');
    const empty = panelOf(rerender(pane, ready, life()));
    assert.equal(empty.props['aria-label'], 'Payer calls');
    assert.match(empty.props.children[2].props.children, /^No recorded calls/);

    empty.props.children[1].props.onChange({ currentTarget: { files: [recording] } });
    await tick();
    const attached = latest();
    const upload = state.requests.find((r) => r.path === `/cases/${CASE}/calls`);
    assert.equal(upload.method, 'POST');
    assert.equal(upload.opts.upload.filename, 'Payer call.wav');
    assert.equal(upload.opts.upload.contentType, 'audio/wav');
    assert.deepEqual(attached.calls, [
      { callId: CALL, label: 'Payer call.wav', state: 'none', window: null, errorCode: null },
    ]);

    const listed = panelOf(rerender(pane, attached, life()));
    const [label, status, transcribe] = itemOf(listed);
    assert.equal(label.props.children, 'Payer call.wav');
    assert.equal(status.props.children, 'Not transcribed yet.');
    assert.equal(transcribe.props.children, 'Transcribe after hours');
    assert.equal(transcribe.props.disabled, false);
    transcribe.props.onClick();
    await tick();
    assert.deepEqual(
      state.requests.filter((r) => r.path.endsWith('/transcribe')).map((r) => r.opts.body),
      [{}],
    );
    const queued = latest();
    assert.equal(queued.calls[0].state, 'queued');
    const shown = itemOf(panelOf(rerender(pane, queued, life())));
    assert.equal(
      shown[1].props.children,
      'Queued for transcription after hours (19:00 to 07:00), on this Mac.',
    );
    assert.equal(shown[2].props.disabled, true, 'a queued call is not queued twice');
    assert.deepEqual(hostAccesses, []);
  });

  test('queueing refusals and failures', async () => {
    const refuse = (failure) =>
      createCaseApi(async (path) => {
        if (path.endsWith('/transcribe')) throw failure;
        return caseBody([call()]);
      });
    const closed = await queueTranscription(refuse(rejection(409, 'case_closed')), CASE, CALL);
    assert.equal(closed.notice, 'case_closed');
    const missing = await queueTranscription(refuse(rejection(404, 'call_not_found')), CASE, CALL);
    assert.equal(missing.notice, 'call_not_found');
    assert.deepEqual(await queueTranscription(refuse(new Error('offline')), CASE, CALL), {
      state: 'unavailable',
      caseId: CASE,
    });
  });

  test('the pane ignores call actions without a ready, open case', () => {
    const idle = rerender({ type: CasePane, props: { rest: async () => ({}) } });
    const panel = panelOf(idle);
    assert.equal(panel.props.children[1].props.disabled, true);
    const element = idle.props.children[at.calls];
    element.props.onAttach([recording]);
    element.props.onTranscribe(CALL);
    assert.equal(hooks.states[0].updates.length, 0);

    const ready = { state: 'ready', caseId: CASE, documents: [], fields: [] };
    const open = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
    const props = open.props.children[at.calls].props;
    props.onAttach(null);
    props.onAttach([]);
    assert.equal(hooks.states[0].updates.length, 0, 'no file, nothing to attach');

    const closed = { ...ready, closed: true };
    const shut = rerender({ type: CasePane, props: { rest: async () => ({}) } }, closed, life());
    const shutProps = shut.props.children[at.calls].props;
    shutProps.onAttach([recording]);
    shutProps.onTranscribe(CALL);
    assert.equal(hooks.states[0].updates.length, 0, 'a closed case takes no calls');
    assert.equal(panelOf(shut).props.children[1].props.disabled, true);
  });
});

describe('US-11.1 a recording is attached', () => {
  test('test_us_11_1_pane_recording_refused', async () => {
    const api = (failure) =>
      createCaseApi(async (path) => {
        if (path.endsWith('/calls')) throw failure;
        return caseBody();
      });
    const notAudio = await addCall(api(rejection(415, 'unsupported_audio')), CASE, recording);
    assert.equal(notAudio.notice, 'unsupported_audio');
    assert.equal(
      REFUSALS.unsupported_audio,
      'ClaimCoach accepts WAV, MP3, FLAC, and M4A call recordings only.',
    );
    assert.deepEqual(await addCall(api(new Error('offline')), CASE, recording), {
      state: 'unavailable',
      caseId: CASE,
    });
    let read = false;
    const big = {
      ...recording,
      size: MAX_CALL_BYTES + 1,
      arrayBuffer: async () => {
        read = true;
        return new ArrayBuffer(0);
      },
    };
    const tooLarge = await addCall(api(new Error('unused')), CASE, big);
    assert.equal(tooLarge.notice, 'call_too_large');
    assert.equal(read, false, 'an oversized recording is never read');
  });

  test('a recording without a type is sent as octet-stream', async () => {
    const requests = [];
    const api = createCaseApi(async (_path, opts) => {
      requests.push(opts);
      return caseBody();
    });
    await addCall(api, CASE, { ...recording, type: '' });
    assert.equal(requests[0].upload.contentType, 'application/octet-stream');
  });
});

describe("US-11.1 the transcript's notes are shown with the case", () => {
  test('test_us_11_1_pane_transcript_notes_shown', async () => {
    const body = caseBody([call(job('done'), TRANSCRIPT)]);
    const ready = await openCase(
      createCaseApi(async () => body),
      CASE,
    );
    const pane = rerender({ type: CasePane, props: { rest: async () => body } }, ready, life());
    const [, status, again, cutOff, reference, instructions, note, details] = itemOf(panelOf(pane));
    assert.equal(status.props.children, 'Transcribed on this Mac.');
    assert.equal(cutOff, null, 'a whole transcript carries no warning');
    assert.equal(again.props.children, 'Transcribe again after hours');
    assert.equal(again.props.disabled, false);
    assert.equal(reference.props.children, 'Reference number: 8417293');
    assert.equal(instructions.props['aria-label'], 'Rep instructions');
    assert.deepEqual(
      instructions.props.children.map((li) => li.props.children),
      ['You need to resubmit.'],
    );
    assert.match(note.props.children, /check them against it/);
    assert.equal(details.type, 'details');
    assert.equal(details.props.children[1].props.children, TRANSCRIPT.text);
  });

  test('a transcript without notes says so', () => {
    const [view] = callsOf(
      caseBody([
        call(job('done'), { text: 'Hello.', reference_number: null, rep_instructions: 7 }),
      ]),
    );
    assert.deepEqual(view.transcript, {
      text: 'Hello.',
      referenceNumber: null,
      instructions: [],
      truncated: false,
    });
    const panel = CallsPanel({
      calls: [view],
      disabled: false,
      closed: false,
      onAttach() {},
      onTranscribe() {},
    });
    const [, , , , reference, instructions] =
      panel.props.children[2].props.children[0].props.children;
    assert.equal(reference.props.children, 'No reference number was heard; check the transcript.');
    assert.equal(
      instructions.props.children,
      'No rep instructions were heard; check the transcript.',
    );
  });
});

describe('US-11.1 review regressions', () => {
  test('a transcript cut off at the length limit says so', () => {
    const [view] = callsOf(caseBody([call(job('done'), { ...TRANSCRIPT, truncated: true })]));
    assert.equal(view.transcript.truncated, true);
    const panel = CallsPanel({
      calls: [view],
      disabled: false,
      closed: false,
      onAttach() {},
      onTranscribe() {},
    });
    const cutOff = panel.props.children[2].props.children[0].props.children[3];
    assert.equal(cutOff.props.role, 'alert');
    assert.match(cutOff.props.children, /stops before the call ended/);
  });

  test('a call whose finished job was forgotten still reads as transcribed', () => {
    const [view] = callsOf(caseBody([call(null, TRANSCRIPT)]));
    assert.equal(view.state, 'done');
    assert.equal(describeCall(view), 'Transcribed on this Mac.');
  });
});

describe('US-11.1 call states and malformed bodies', () => {
  test('describeCall covers every state', () => {
    const base = { callId: CALL, label: 'x', window: null, errorCode: null };
    assert.equal(
      describeCall({ ...base, state: 'queued' }),
      'Queued for transcription after hours, on this Mac.',
    );
    assert.equal(describeCall({ ...base, state: 'running' }), 'Transcribing on this Mac…');
    assert.equal(
      describeCall({ ...base, state: 'failed', errorCode: 'model_unavailable' }),
      `Not transcribed: ${REFUSALS.model_unavailable}`,
    );
    assert.equal(
      describeCall({ ...base, state: 'failed', errorCode: 'mystery' }),
      `Not transcribed: ${REFUSALS.transcription_failed}`,
    );
  });

  test('a running call cannot be queued again', () => {
    const [view] = callsOf(caseBody([call(job('running'))]));
    const panel = CallsPanel({
      calls: [view],
      disabled: false,
      closed: false,
      onAttach() {},
      onTranscribe() {},
    });
    assert.equal(panel.props.children[2].props.children[0].props.children[2].props.disabled, true);
  });

  test('malformed calls are skipped or read safely', () => {
    assert.deepEqual(callsOf(null), []);
    assert.deepEqual(callsOf({ calls: 'x' }), []);
    assert.deepEqual(
      callsOf({ calls: [null, { recording: null }, { recording: { call_id: 7 } }] }),
      [],
    );
    const [odd] = callsOf({
      calls: [
        {
          recording: { call_id: CALL, filename: null },
          transcription: { state: 'paused', window: { start_hour: 25, end_hour: 7 } },
          transcript: { text: 9 },
        },
      ],
    });
    assert.deepEqual(odd, {
      callId: CALL,
      label: 'Call recording',
      state: 'none',
      window: null,
      errorCode: null,
    });
    const [partial] = callsOf({
      calls: [
        {
          recording: { call_id: CALL },
          transcription: { state: 'failed', window: null, error_code: 'model_unavailable' },
        },
      ],
    });
    assert.equal(partial.state, 'failed');
    assert.equal(partial.window, null);
    assert.equal(partial.errorCode, 'model_unavailable');
  });
});
