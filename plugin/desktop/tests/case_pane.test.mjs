/**
 * node --test suite for the case pane. US-3.3 scenarios:
 *   - Pane case actions use only plugin REST calls
 *   - Case processing adds nothing to agent sessions
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  createCaseApi,
  describeCase,
  openCase,
  processCase,
  uploadCase,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses, sessions } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const PLUGIN_JS = new URL('../plugin.js', import.meta.url);
const tick = () => new Promise((resolve) => setImmediate(resolve));
const file = {
  name: 'eob.pdf',
  type: 'application/pdf',
  arrayBuffer: async () => new TextEncoder().encode('%PDF synthetic').buffer,
};

/** A backend that answers the case routes the way plugin_api will (EPIC-5). */
const caseBackend = async (path, opts) => {
  if (path === '/health') return { ok: true, status: 'ok', version: '0.1.0' };
  if (path === '/cases' && opts?.method === 'POST') return { ok: true, case_id: 'case_0001' };
  if (path === '/cases/case_0001') return { ok: true, case_id: 'case_0001' };
  return { ok: true };
};

/** Render the registered pane, pick a file, and return the case state the pane ends in. */
async function uploadFromPane(ctx) {
  const element = byArea(ctx.recorded).panes[0].render();
  const pane = element.type(element.props);
  pane.props.children[2].props.onChange({ currentTarget: { files: [file] } });
  await tick();
  return { element, state: hooks.states[0].updates.at(-1) }; // slot 0: the case state
}

afterEach(runCleanups);

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-3.3 pane case actions use only plugin REST calls', () => {
  test('test_us_3_3_pane_uses_only_plugin_rest', async () => {
    const ctx = createFakeCtx({ rest: caseBackend });
    plugin.register(ctx);
    const { state } = await uploadFromPane(ctx);
    assert.deepEqual(state, { state: 'ready', caseId: 'case_0001', documents: [], fields: [] });

    assert.deepEqual(
      ctx.recorded.restRequests.map((r) => [r.method, r.path]),
      [
        ['POST', '/cases'],
        ['POST', '/cases/case_0001/documents'],
        ['GET', '/cases/case_0001'],
      ],
    );
    const upload = ctx.recorded.restRequests[1].opts.upload;
    assert.equal(upload.filename, 'eob.pdf');
    assert.equal(upload.contentType, 'application/pdf');
    assert.deepEqual(hostAccesses, [], 'no host.composer, host.request, or session call');
  });

  test('test_us_3_3_plugin_js_never_references_agent_surfaces', async () => {
    const source = await readFile(PLUGIN_JS, 'utf8');
    const sdkImport = source.match(/import\s*\{([^}]*)\}\s*from\s*'@hermes\/plugin-sdk'/);
    assert.ok(sdkImport, 'plugin.js imports the SDK');
    const names = sdkImport[1].split(',').map((n) => n.trim());
    assert.ok(!names.includes('host'), 'host is never imported');
    const code = source.replace(/\/\*\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    for (const surface of [/\bhost\b/, /\bcomposer\b/, /\.request\(/, /\bsessions?\b/]) {
      assert.doesNotMatch(code, surface);
    }
  });
});

describe('US-3.3 case processing adds nothing to agent sessions', () => {
  test('test_us_3_3_case_processing_adds_nothing_to_sessions', async () => {
    const before = structuredClone(sessions);
    const ctx = createFakeCtx({ rest: caseBackend });
    plugin.register(ctx);
    const { element, state: ready } = await uploadFromPane(ctx);
    // React re-renders the pane with the new state; then the biller presses Process.
    resetHooks();
    hooks.seed = [ready];
    const rerendered = element.type(element.props);
    assert.equal(rerendered.props.children[4].props.disabled, false);
    rerendered.props.children[4].props.onClick();
    await tick();

    assert.deepEqual(hooks.states[0].updates.at(-1), {
      state: 'processing',
      caseId: 'case_0001',
      progress: 0,
    });
    assert.deepEqual(ctx.recorded.restRequests.at(-1), {
      path: '/cases/case_0001/process',
      method: 'POST',
      opts: { method: 'POST', body: {} },
    });
    assert.deepEqual(sessions, before, 'no message or tool call was added to any session');
    assert.deepEqual(hostAccesses, []);
  });
});

describe('case API and pane states', () => {
  test('a second pick while uploading is ignored and late answers are dropped', async () => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const calls = [];
    const rest = async (path, opts) => {
      calls.push(path);
      await gate;
      return caseBackend(path, opts);
    };
    hooks.seed = [{ state: 'busy' }];
    const busy = CasePane({ rest });
    assert.equal(busy.props.children[2].props.disabled, true);
    busy.props.children[2].props.onChange({ currentTarget: { files: [file] } });
    assert.deepEqual(calls, [], 'no upload starts while one is running');

    resetHooks();
    const pane = CasePane({ rest });
    pane.props.children[2].props.onChange({ currentTarget: { files: [file] } });
    const caseSlot = hooks.states[0];
    runCleanups(); // the pane unmounts before the backend answers
    release();
    await tick();
    await tick();
    assert.deepEqual(caseSlot.updates, [{ state: 'busy' }], 'no update after unmount');
  });

  test('only the latest action updates the pane', async () => {
    const answers = [];
    const rest = (path, opts) =>
      new Promise((resolve) => answers.push(() => resolve(caseBackend(path, opts))));
    hooks.seed = [{ state: 'ready', caseId: 'case_0001', documents: [], fields: [] }];
    const pane = CasePane({ rest });
    pane.props.children[4].props.onClick(); // first Process
    pane.props.children[4].props.onClick(); // double click
    answers[1]();
    await tick();
    answers[0]();
    await tick();
    const updates = hooks.states[0].updates;
    assert.deepEqual(updates, [
      { state: 'busy' },
      { state: 'busy' },
      { state: 'processing', caseId: 'case_0001', progress: 0 },
    ]);
  });

  test('uploadCase reports unavailable when the backend has no case routes yet', async () => {
    const api = createCaseApi(async () => {
      throw new Error('404 {"ok":false,"error":{"code":"not_found"}}');
    });
    assert.deepEqual(await uploadCase(api, file), { state: 'unavailable' });
    assert.deepEqual(await processCase(api, 'c1'), { state: 'unavailable' });
  });

  test('uploadCase rejects a malformed case id and openCase a mismatched one', async () => {
    const bad = createCaseApi(async () => ({ ok: true, case_id: 'Jane Doe' }));
    assert.deepEqual(await uploadCase(bad, file), { state: 'unavailable' });
    const other = createCaseApi(async () => ({ ok: true, case_id: 'case_2' }));
    assert.deepEqual(await openCase(other, 'case_1'), { state: 'unavailable' });
    const broken = createCaseApi(async () => {
      throw new Error('503');
    });
    assert.deepEqual(await openCase(broken, 'case_1'), { state: 'unavailable' });
  });

  test('uploadCase defaults the content type and encodes the case id', async () => {
    const calls = [];
    const api = createCaseApi(async (path, opts) => {
      calls.push([path, opts]);
      return { ok: true, case_id: 'a-b_c' };
    });
    await uploadCase(api, { ...file, type: '' });
    assert.equal(calls[1][0], '/cases/a-b_c/documents');
    assert.equal(calls[1][1].upload.contentType, 'application/octet-stream');
    assert.equal(createCaseApi(async (p) => p).getCase('x/y') instanceof Promise, true);
    assert.equal(await createCaseApi(async (p) => p).getCase('x/y'), '/cases/x%2Fy');
  });

  test('the pane ignores an empty file pick and Process before a case is ready', async () => {
    const calls = [];
    const element = CasePane({ rest: async (path) => calls.push(path) });
    const [, , input, status, button] = element.props.children;
    input.props.onChange({ currentTarget: { files: [] } });
    input.props.onChange({ currentTarget: { files: null } });
    button.props.onClick();
    await tick();
    assert.equal(button.props.disabled, true);
    assert.match(status.props.children, /Drop a denial document/);
    assert.deepEqual(calls, [], 'nothing is sent without a picked file');
  });

  test('describeCase covers every state', () => {
    assert.match(describeCase({ state: 'busy' }), /Uploading/);
    assert.match(describeCase({ state: 'ready', caseId: 'c1' }), /c1 is ready/);
    assert.match(describeCase({ state: 'processing', caseId: 'c1' }), /on this Mac/);
    assert.match(describeCase({ state: 'unavailable' }), /not available/);
  });
});
