/**
 * node --test suite for plugin.js. US-1.4 scenarios:
 *   - plugin.js registers its contributions against a fake ctx
 *   - plugin.js imports only allowed specifiers
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  DASHBOARD_PATH,
  DashboardPage,
  describeWorker,
  LocalOnlyIndicator,
  loadWorkerState,
  PLUGIN_ID,
  SettingsPage,
  WorkerStatus,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const ALLOWED = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime']);
const PLUGIN_JS = new URL('../plugin.js', import.meta.url);
const healthy = async () => ({ ok: true, status: 'ok', version: '0.1.0' });
const tick = () => new Promise((resolve) => setImmediate(resolve));

beforeEach(resetHooks);
afterEach(runCleanups);

describe('US-1.4 registration contract', () => {
  test('test_us_1_4_plugin_js_registers_contributions', () => {
    const ctx = createFakeCtx();
    plugin.register(ctx);
    const areas = byArea(ctx.recorded);

    assert.equal(plugin.id, PLUGIN_ID);
    assert.equal(plugin.defaultEnabled, false, 'PC-1: the desktop half ships opt-in');
    assert.deepEqual(
      areas.panes.map((c) => [c.id, c.data.placement]),
      [['case-pane', 'right']],
    );
    assert.deepEqual(areas.routes[0].data, { path: DASHBOARD_PATH });
    assert.equal(areas['sidebar.nav'][0].data.path, DASHBOARD_PATH);
    assert.equal(areas['statusbar.right'][0].id, 'local-only');
    assert.deepEqual(
      ctx.recorded.settingsPages.map((p) => p.id),
      ['settings'],
    );
    for (const c of [...ctx.recorded.contributions, ...ctx.recorded.settingsPages]) {
      if (c.render) assert.equal(typeof c.render().type, 'function', `${c.id} renders a component`);
    }
  });

  test('registers without a settings page on hosts that lack registerSettingsPage', () => {
    const ctx = createFakeCtx({ settingsPages: false });
    plugin.register(ctx);
    assert.equal(ctx.recorded.contributions.length, 4);
    assert.equal(ctx.recorded.settingsPages.length, 0);
  });

  test('pane and settings renders reach the backend through ctx.rest', async () => {
    const ctx = createFakeCtx({ rest: healthy });
    plugin.register(ctx);
    const pane = byArea(ctx.recorded).panes[0].render();
    const page = ctx.recorded.settingsPages[0].render();
    WorkerStatus(pane.type(pane.props).props.children[1].props);
    WorkerStatus(page.type(page.props).props.children[1].props);
    await tick();
    assert.deepEqual(ctx.recorded.restCalls, ['/health', '/health']);
  });
});

describe('US-1.4 allowed imports (PC-3)', () => {
  test('test_us_1_4_plugin_js_allowed_imports', async () => {
    const source = await readFile(PLUGIN_JS, 'utf8');
    const specifiers = [
      ...source.matchAll(/^\s*import\s[^'"]*?['"]([^'"]+)['"]/gm),
      ...source.matchAll(/\bimport\(\s*['"]([^'"]+)['"]\s*\)/g),
      ...source.matchAll(/^\s*export\s[^'"]*?\sfrom\s+['"]([^'"]+)['"]/gm),
    ].map((m) => m[1]);
    assert.ok(specifiers.length > 0, 'scan found the imports');
    assert.deepEqual(
      specifiers.filter((s) => !ALLOWED.has(s)),
      [],
    );
    assert.ok(source.startsWith('// @ts-check'), 'plugin.js is type-checked (ES-1)');
  });
});

describe('worker status', () => {
  test('loadWorkerState reports a healthy worker', async () => {
    assert.deepEqual(await loadWorkerState(healthy), { state: 'ok', version: '0.1.0' });
  });

  test('loadWorkerState treats a rejected request as unavailable', async () => {
    const rest = async () => {
      throw new Error('503 {"ok":false,"error":{"code":"worker_unavailable"}}');
    };
    assert.deepEqual(await loadWorkerState(rest), { state: 'unavailable' });
  });

  test('loadWorkerState treats an unexpected body as unavailable', async () => {
    assert.deepEqual(await loadWorkerState(async () => null), { state: 'unavailable' });
    assert.deepEqual(await loadWorkerState(async () => ({ ok: true })), { state: 'unavailable' });
  });

  test('describeWorker covers every state', () => {
    assert.match(describeWorker({ state: 'ok', version: '1.2.3' }), /v1\.2\.3/);
    assert.match(describeWorker({ state: 'loading' }), /Checking/);
    assert.match(describeWorker({ state: 'unavailable' }), /not running/);
  });

  test('WorkerStatus starts loading and updates when health arrives', async () => {
    const element = WorkerStatus({ rest: healthy });
    assert.equal(element.props.role, 'status');
    assert.match(element.props.children, /Checking/);
    await tick();
    assert.deepEqual(hooks.states[0].updates, [{ state: 'ok', version: '0.1.0' }]);
  });

  test('WorkerStatus ignores a response that arrives after unmount', async () => {
    WorkerStatus({ rest: healthy });
    for (const cleanup of hooks.cleanups) cleanup();
    await tick();
    assert.deepEqual(hooks.states[0].updates, []);
  });
});

describe('views', () => {
  test('CasePane and SettingsPage embed the worker status', () => {
    for (const View of [CasePane, SettingsPage]) {
      const element = View({ rest: healthy });
      const [heading, status] = element.props.children;
      assert.equal(heading.props.children, 'ClaimCoach');
      assert.equal(status.type, WorkerStatus);
    }
  });

  test('DashboardPage renders static content and the indicator starts local-only', () => {
    const page = DashboardPage({ rest: async () => ({}) });
    assert.equal(page.props.children[0].props.children, 'ClaimCoach dashboard');
    const indicator = LocalOnlyIndicator({ rest: healthy });
    assert.equal(indicator.props.children, 'Local-only');
    assert.match(indicator.props.title, /never leaves this Mac/);
  });
});
