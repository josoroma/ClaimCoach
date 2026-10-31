/**
 * node --test suite for extraction in the pane. US-5.2 scenarios:
 *   - Unreadable fields are highlighted
 *   - Confirmed fields are stored as confirmed
 *   - Extraction progress is pushed as events
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  confirmField,
  createCaseApi,
  describeCase,
  FieldList,
  fieldLabel,
  fieldsOf,
  openCase,
  PROGRESS_EVENT,
  processCase,
  progressOf,
  REFUSALS,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const JOB = 'job_0123456789abcdef';
const at = { status: 3, process: 4, refresh: 9, fields: 10 };

const read = (value) => ({ value, status: 'extracted' });
const unreadable = { value: null, status: 'unreadable' };
const pdfFile = {
  name: 'eob.pdf',
  type: 'application/pdf',
  arrayBuffer: async () => new TextEncoder().encode('%PDF-1.7').buffer,
};

/** A case body as `GET /cases/{id}` returns it after extraction. */
function caseBody(claimId = unreadable) {
  return {
    ok: true,
    case_id: CASE,
    documents: [{ doc_id: 'src_0', kind: 'pdf', filename: 'eob.pdf' }],
    extraction: {
      payer_name: read('ACME HEALTH PLAN'),
      claim_id: claimId,
      billed_amount: read('250.00'),
      paid_amount: read('0.00'),
      adjustments: [],
      rarc_codes: [],
      lines: [
        {
          procedure_code: read('99213'),
          service_date: read('2026-09-01'),
          billed_amount: read('250.00'),
          paid_amount: read('0.00'),
          adjustments: [{ group_code: read('CO'), carc: read('197'), amount: read('250.00') }],
          rarc_codes: [read('N286')],
        },
      ],
      other_claims: 0,
      sources: ['src_0'],
    },
    needs_confirmation: claimId.status === 'unreadable' ? ['claim_id'] : [],
  };
}

/** A worker that extracts on Process and confirms fields, as plugin_api does. */
function backend() {
  const state = { body: caseBody(), confirmed: [] };
  const rest = async (path, opts) => {
    if (path === `/cases/${CASE}/process`) {
      state.body = caseBody();
      return { ok: true, case_id: CASE, job_id: JOB };
    }
    if (path === `/cases/${CASE}/fields`) {
      state.confirmed.push(opts.body);
      state.body = caseBody({ value: opts.body.value, status: 'confirmed' });
      return state.body;
    }
    if (path === `/cases/${CASE}`) return state.body;
    return { ok: true, status: 'ok', version: '0.1.0' };
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

const fieldItems = (pane) => pane.props.children[at.fields];

afterEach(runCleanups);

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-5.2 unreadable fields are highlighted', () => {
  test('test_us_5_2_pane_unreadable_fields_highlighted', async () => {
    const ready = await openCase(createCaseApi(backend().rest), CASE);
    assert.equal(ready.state, 'ready');
    const element = { type: CasePane, props: { rest: backend().rest } };
    const pane = rerender(element, ready, life());
    const list = fieldItems(pane);
    const rendered = list.type(list.props);
    assert.equal(rendered.props['aria-label'], 'Extracted fields');
    const items = rendered.props.children;
    const claim = items.find((li) => li.props['data-status'] === 'unreadable');
    assert.equal(claim.props['aria-invalid'], true);
    assert.deepEqual(claim.props.style, { outline: '2px solid #d97706', background: '#fef3c7' });
    assert.equal(claim.props.children[0].props.children, 'Claim number (needs confirmation)');
    const others = items.filter((li) => li !== claim);
    assert.ok(others.every((li) => li.props['aria-invalid'] === false && !li.props.style));
    assert.match(describeCase(ready), /1 field\(s\) need confirmation/);
  });

  test('fields are flattened in document order with readable labels', () => {
    const fields = fieldsOf(caseBody().extraction);
    assert.deepEqual(
      fields.map((f) => f.label),
      [
        'Payer',
        'Claim number',
        'Billed',
        'Paid',
        'Line 1 · Procedure code',
        'Line 1 · Service date',
        'Line 1 · Billed',
        'Line 1 · Paid',
        'Line 1 · Adjustment 1 · Group code',
        'Line 1 · Adjustment 1 · CARC',
        'Line 1 · Adjustment 1 · Amount',
        'Line 1 · RARC 1',
      ],
    );
    assert.equal(fields[1].path, 'claim_id');
    assert.equal(fields[1].value, '');
    assert.equal(fieldLabel('mystery.2'), 'mystery 3');
    assert.deepEqual(fieldsOf(null), []);
    assert.deepEqual(fieldsOf({ status: 'extracted', value: 'x' }), [], 'a root is no field');
    assert.deepEqual(fieldsOf({ x: { status: 'other', value: 'y' } }), []);
  });

  test('an 835 with more claims says so', async () => {
    const body = caseBody(read('CLAIM-77'));
    body.extraction.other_claims = 2;
    const ready = await openCase(
      createCaseApi(async () => body),
      CASE,
    );
    assert.equal(ready.otherClaims, 2);
    assert.match(describeCase(ready), /every field is read or confirmed\. This 835 holds 2 more/);
  });
});

describe('US-5.2 confirmed fields are stored as confirmed', () => {
  test('test_us_5_2_pane_confirmed_fields_stored', async () => {
    const { rest, state } = backend();
    const ready = await openCase(createCaseApi(rest), CASE);
    const element = { type: CasePane, props: { rest } };

    // The biller types the claim number; React re-renders with the edit; then Confirm.
    const typing = rerender(element, ready, life());
    const field = (pane) =>
      fieldItems(pane)
        .type(fieldItems(pane).props)
        .props.children.find((li) => li.props.children[1].props['aria-label'] === 'Claim number');
    field(typing).props.children[1].props.onChange({ currentTarget: { value: 'CLAIM-77' } });
    assert.deepEqual(hooks.states[3].updates, [{ claim_id: 'CLAIM-77' }]);

    const pane = rerender(element, ready, life(), '', { claim_id: 'CLAIM-77' });
    const button = field(pane).props.children[2];
    assert.equal(button.props.disabled, false);
    button.props.onClick();
    await tick();
    assert.deepEqual(state.confirmed, [{ path: 'claim_id', value: 'CLAIM-77' }]);
    assert.deepEqual(hooks.states[3].updates, [{}], 'the edit is cleared');
    const stored = hooks.states[0].updates.at(-1);
    const claim = stored.fields.find((f) => f.path === 'claim_id');
    assert.deepEqual(claim, {
      path: 'claim_id',
      label: 'Claim number',
      value: 'CLAIM-77',
      status: 'confirmed',
    });

    const shown = rerender(element, stored, life());
    const item = field(shown);
    assert.equal(item.props['data-status'], 'confirmed');
    assert.equal(item.props['aria-invalid'], false);
    assert.equal(item.props.children[2].props.children, 'Confirmed');
    assert.match(describeCase(stored), /every field is read or confirmed/);
    assert.deepEqual(hostAccesses, []);
  });

  test('a refused value keeps the case and explains it with fixed text', async () => {
    const { rest } = backend();
    const failing = (code) =>
      createCaseApi(async (path, opts) => {
        if (path.endsWith('/fields')) {
          throw new Error(`422: {"ok":false,"error":{"code":"${code}","message":"Jane Doe"}}`);
        }
        return rest(path, opts);
      });
    const invalid = await confirmField(failing('invalid_request'), CASE, 'claim_id', 'x y');
    assert.equal(invalid.notice, 'invalid_value');
    assert.ok(describeCase(invalid).startsWith(REFUSALS.invalid_value));
    const closed = await confirmField(failing('case_closed'), CASE, 'claim_id', 'A');
    assert.equal(closed.notice, 'case_closed');
    assert.deepEqual(await confirmField(failing('worker_error'), CASE, 'claim_id', 'A'), {
      state: 'unavailable',
    });
    const other = createCaseApi(async () => ({ ok: true, case_id: 'case_other' }));
    assert.deepEqual(await confirmField(other, CASE, 'claim_id', 'A'), { state: 'unavailable' });
  });

  test('Confirm does nothing without a value or an open case', async () => {
    const calls = [];
    const rest = async (path, opts) => {
      calls.push(path);
      return backend().rest(path, opts);
    };
    const ready = await openCase(createCaseApi(backend().rest), CASE);
    const element = { type: CasePane, props: { rest } };
    const pane = rerender(element, ready, life(), '', { claim_id: '   ' });
    const list = fieldItems(pane);
    list.props.onConfirm('claim_id');
    list.props.onConfirm('no.such.field');
    await tick();
    assert.deepEqual(calls, []);
    list.props.onConfirm('payer_name'); // confirming a read value as it is
    await tick();
    assert.deepEqual(calls, [`/cases/${CASE}/fields`]);
    calls.length = 0;
    const busy = rerender(element, { state: 'busy' }, life());
    fieldItems(busy).props.onConfirm('claim_id');
    assert.deepEqual(fieldItems(busy).props.fields, []);
    await tick();
    assert.deepEqual(calls, []);
    const rendered = FieldList({
      fields: ready.fields,
      edits: {},
      onEdit() {},
      onConfirm() {},
      disabled: true,
    });
    assert.ok(rendered.props.children.every((li) => li.props.children[2].props.disabled));
  });
});

describe('US-5.2 extraction progress is pushed as events', () => {
  test('test_us_5_2_pane_receives_progress_events', async () => {
    const { rest } = backend();
    const ctx = createFakeCtx({ rest, events: true });
    plugin.register(ctx);
    const element = byArea(ctx.recorded).panes[0].render();
    const ready = await openCase(createCaseApi(rest), CASE);
    const pane = rerender(element, ready, life());
    assert.deepEqual(
      ctx.recorded.listeners.map((l) => l.type),
      [PROGRESS_EVENT],
    );

    pane.props.children[at.process].props.onClick();
    await tick();
    assert.deepEqual(hooks.states[0].updates.at(-1), {
      state: 'processing',
      caseId: CASE,
      progress: 0,
    });
    const before = hooks.states[0].updates.length;
    ctx.emit(PROGRESS_EVENT, {
      case_id: 'case_ffffffffffffffff',
      job_id: JOB,
      stage: 'extracting',
      progress: 0.5,
    });
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, stage: 'extracting' });
    ctx.emit('plugin.other.case.progress', { case_id: CASE, stage: 'done', progress: 1 });
    assert.equal(hooks.states[0].updates.length, before, 'other cases and bad payloads ignored');

    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'extracting', progress: 0.475 });
    const progressing = hooks.states[0].updates.at(-1);
    assert.deepEqual(progressing, { state: 'processing', caseId: CASE, progress: 0.475 });
    assert.match(describeCase(progressing), /48%/);

    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'done', progress: 1 });
    await tick();
    const done = hooks.states[0].updates.at(-1);
    assert.equal(done.state, 'ready');
    assert.deepEqual(
      done.fields.filter((f) => f.status === 'unreadable').map((f) => f.path),
      ['claim_id'],
    );
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'done', progress: 1 });
    await tick();
    assert.equal(hooks.states[0].updates.at(-1), done, 'a late duplicate is ignored');

    runCleanups();
    assert.deepEqual(ctx.recorded.listeners, [], 'the pane unsubscribes when it unmounts');
    assert.deepEqual(hostAccesses, [], 'events come through ctx.onEvent, never host (US-3.3)');
  });

  test('a failed job reopens the case with its fixed explanation', async () => {
    const { rest } = backend();
    const ctx = createFakeCtx({ rest, events: true });
    plugin.register(ctx);
    const element = byArea(ctx.recorded).panes[0].render();
    for (const [code, notice] of [
      ['model_unavailable', 'model_unavailable'],
      [null, 'extraction_failed'],
      ['internal_error', 'extraction_failed'],
    ]) {
      const pane = rerender(
        element,
        { state: 'ready', caseId: CASE, documents: [], fields: [] },
        life(),
      );
      pane.props.children[at.process].props.onClick();
      await tick();
      ctx.emit(PROGRESS_EVENT, {
        case_id: CASE,
        job_id: JOB,
        stage: 'failed',
        progress: 0.2,
        error_code: code,
      });
      await tick();
      assert.equal(hooks.states[0].updates.at(-1).notice, notice);
      runCleanups();
    }
  });

  test('events after unmount are ignored; hosts without onEvent still load', async () => {
    const { rest } = backend();
    const ctx = createFakeCtx({ rest, events: true });
    plugin.register(ctx);
    const element = byArea(ctx.recorded).panes[0].render();
    const pane = rerender(
      element,
      { state: 'ready', caseId: CASE, documents: [], fields: [] },
      life(),
    );
    pane.props.children[at.process].props.onClick();
    await tick();
    const remembered = hooks.states[1].value;
    remembered.live = false;
    const count = hooks.states[0].updates.length;
    remembered.onProgress({ case_id: CASE, job_id: JOB, stage: 'done', progress: 1 });
    assert.equal(hooks.states[0].updates.length, count);

    const bare = createFakeCtx({ rest });
    plugin.register(bare);
    const plain = byArea(bare.recorded).panes[0].render();
    const unsubscribe = plain.props.subscribe(() => {});
    assert.equal(typeof unsubscribe, 'function');
    unsubscribe();
    assert.equal(CasePane({ rest }).props.children.length, 11, 'subscribe defaults to no events');
  });

  test('Refresh while processing stops listening for that job and reopens the case', async () => {
    const { rest } = backend();
    const element = { type: CasePane, props: { rest } };
    const processing = { state: 'processing', caseId: CASE, progress: 0.4 };
    const remembered = { ...life(), processing: CASE };
    const pane = rerender(element, processing, remembered);
    assert.equal(pane.props.children[at.refresh].props.disabled, false);
    pane.props.children[at.refresh].props.onClick();
    await tick();
    assert.equal(remembered.processing, null);
    assert.equal(hooks.states[0].updates.at(-1).state, 'ready');
  });

  test('progressOf keeps only well-formed payloads', () => {
    assert.equal(progressOf(null), null);
    assert.equal(progressOf({ case_id: CASE, stage: 'done', progress: '1' }), null);
    assert.deepEqual(progressOf({ case_id: CASE, stage: 'failed', progress: 0, error_code: 'x' }), {
      caseId: CASE,
      stage: 'failed',
      progress: 0,
      errorCode: 'x',
    });
  });

  test('Process explains a refusal and describes progress without a value', async () => {
    const api = createCaseApi(async (path) => {
      if (path.endsWith('/process')) {
        throw new Error('409: {"ok":false,"error":{"code":"no_documents"}}');
      }
      return { ok: true, case_id: CASE, documents: [] };
    });
    const state = await processCase(api, CASE);
    assert.equal(state.notice, 'no_documents');
    assert.match(describeCase({ state: 'processing', caseId: CASE }), / 0%$/);
  });
});

describe('US-5.2 review regressions', () => {
  test('values typed for one case never show in another', async () => {
    const other = 'case_ffffffffffffffff';
    const rest = async (path) => {
      if (path === '/cases') return { ok: true, case_id: other, documents: [] };
      if (path.endsWith('/documents')) return { ok: true };
      return { ...caseBody(), case_id: other };
    };
    const element = { type: CasePane, props: { rest } };
    const ready = await openCase(createCaseApi(backend().rest), CASE);

    // New case drops the edits.
    const pane = rerender(element, ready, life(), '', { claim_id: 'CLAIM-A' });
    pane.props.children[5].props.onClick();
    assert.deepEqual(hooks.states[3].updates, [{}]);

    // A drop that lands in another case drops them too.
    const fresh = rerender(element, { state: 'idle' }, life(null), '', { claim_id: 'CLAIM-A' });
    fresh.props.onDrop({ preventDefault() {}, dataTransfer: { files: [pdfFile] } });
    await tick();
    assert.equal(hooks.states[0].updates.at(-1).caseId, other);
    assert.deepEqual(hooks.states[3].updates, [{}]);

    // Refresh shows the stored values again, so no typed value hides them.
    const same = rerender(element, ready, life(other), '', { claim_id: 'CLAIM-A' });
    same.props.children[at.refresh].props.onClick();
    await tick();
    assert.deepEqual(hooks.states[3].updates, [{}], 'Refresh shows the stored values');
  });

  test('a finished run replaces anything typed before it', async () => {
    const { rest } = backend();
    const ctx = createFakeCtx({ rest, events: true });
    plugin.register(ctx);
    const element = byArea(ctx.recorded).panes[0].render();
    const ready = { state: 'ready', caseId: CASE, documents: [], fields: [] };
    const pane = rerender(element, ready, life(), '', { claim_id: 'OLD' });
    pane.props.children[at.process].props.onClick();
    await tick();
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'done', progress: 1 });
    await tick();
    assert.deepEqual(hooks.states[3].updates, [{}]);
    runCleanups();
  });

  test('documents that could not be read are named in the status', async () => {
    const body = caseBody(read('CLAIM-77'));
    body.extraction.unread_sources = ['src_0'];
    const ready = await openCase(
      createCaseApi(async () => body),
      CASE,
    );
    assert.equal(ready.unreadSources, 1);
    assert.match(describeCase(ready), /1 document\(s\) could not be read/);
    body.extraction.unread_sources = [];
    assert.equal(
      (
        await openCase(
          createCaseApi(async () => body),
          CASE,
        )
      ).unreadSources,
      undefined,
    );
  });
});
