/**
 * node --test suite for EPIC-10 Desktop UI.
 *
 * US-10.1 scenarios:
 *   - The case pane is registered (case list and case detail views)
 *   - The dashboard route is registered
 *   - Backend errors render as an error state
 * US-10.2 scenarios:
 *   - Indicator shows local-only by default
 * US-10.3 scenarios:
 *   - Settings page registers when supported
 *   - Settings degrade when unsupported
 *   - Retention setting is saved
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CASE_LIST_UNAVAILABLE,
  CaseListView,
  CasePane,
  ClaimCoachPane,
  CorpusSection,
  casesOf,
  corpusOf,
  createCaseApi,
  DASHBOARD_PATH,
  DashboardPage,
  describeCaseRow,
  describeSave,
  indicatorView,
  LocalOnlyIndicator,
  loadCaseList,
  loadCorpus,
  loadIndicatorState,
  loadModels,
  loadRetention,
  ModelsSection,
  modelsOf,
  parseDays,
  RetentionSection,
  SETTINGS_REFUSALS,
  SettingsPage,
  saveRetention,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const OTHER = 'case_fedcba9876543210';

/** A Hermes `ctx.rest` rejection carrying an envelope code. */
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'secret text' } })}`);

const listBody = {
  ok: true,
  cases: [
    {
      case_id: OTHER,
      opened_at: '2026-10-31T12:00:00Z',
      closed_at: '2026-10-31T12:00:00Z',
      purged_at: null,
      outcome: 'overturned',
      documents: 2,
      calls: 1,
      extracted: true,
      diagnosed: true,
      drafted: true,
    },
    {
      case_id: CASE,
      opened_at: '2026-10-30T12:00:00Z',
      closed_at: null,
      purged_at: null,
      outcome: null,
      documents: 1,
      calls: 0,
      extracted: false,
      diagnosed: false,
      drafted: false,
    },
  ],
};

const caseBody = (caseId) => ({
  ok: true,
  case_id: caseId,
  opened_at: '2026-10-30T12:00:00Z',
  closed_at: null,
  documents: [],
  extraction: null,
});

/** A backend that answers the case list, a case, and the settings page's reads. */
function backend({ fail = null } = {}) {
  const requests = [];
  const rest = async (path, opts) => {
    requests.push({ path, method: opts?.method ?? 'GET', body: opts?.body });
    if (fail?.(path)) throw rejection(503, 'worker_unavailable');
    if (path === '/cases' && !opts) return listBody;
    if (path.startsWith('/cases/')) return caseBody(decodeURIComponent(path.slice(7)));
    if (path === '/health') return { ok: true, status: 'ok', version: '0.1.0' };
    return {};
  };
  return { rest, requests };
}

function rerender(element, ...seed) {
  resetHooks();
  hooks.seed = seed;
  return element.type(element.props);
}

afterEach(() => runCleanups());

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-10.1 the case pane is registered', () => {
  test('test_us_10_1_case_pane_registered', () => {
    const ctx = createFakeCtx({ events: true });
    plugin.register(ctx);
    const [pane] = byArea(ctx.recorded).panes;
    assert.equal(pane.id, 'case-pane');
    assert.deepEqual(pane.data, { placement: 'right', width: '380px' });
    const element = pane.render();
    assert.equal(element.type, ClaimCoachPane);
    const rendered = element.type(element.props);
    assert.equal(rendered.props['aria-label'], 'ClaimCoach');
    const [list, detail] = rendered.props.children;
    assert.equal(list.type, CaseListView, 'the case list view');
    assert.equal(detail.type, CasePane, 'the case detail view');
    assert.equal(list.props.link, detail.props.link, 'one link joins the two views');
    assert.equal(typeof detail.props.subscribe, 'function');
  });

  test('test_us_10_1_listed_case_opens', async () => {
    const { rest, requests } = backend();
    const pane = rerender({ type: ClaimCoachPane, props: { rest } });
    const [listElement, detailElement] = pane.props.children;
    const { link } = listElement.props;

    // The detail view sets link.open on render; the list calls it.
    const detail = rerender(detailElement);
    assert.equal(typeof link.open, 'function');
    const list = rerender(
      listElement,
      { state: 'ok', cases: casesOf(listBody) },
      { live: true, read: 0 },
    );
    const items = list.props.children[1].props.children;
    assert.equal(items.length, 2);
    assert.equal(
      items[0].props.children.props.children,
      `${OTHER}: opened 2026-10-31 · Appeal drafted · 2 document(s) · 1 call(s) · Overturned · closed`,
    );
    rerender(detailElement);
    items[1].props.children.props.onClick();
    await tick();
    assert.ok(
      requests.some((r) => r.path === `/cases/${CASE}`),
      'the detail view opened it',
    );
    assert.equal(requests.at(-1).path, '/cases', 'and the list reloaded');
    const opened = hooks.states[0].updates.at(-1);
    assert.equal(opened.state, 'ready');
    assert.equal(opened.caseId, CASE);
    assert.ok(detail, 'rendered');
    assert.deepEqual(hostAccesses, []);
  });

  test('the detail view reloads the list when it moves to another case', async () => {
    const { rest, requests } = backend();
    const link = { open() {}, changed() {} };
    let changes = 0;
    const detail = { type: CasePane, props: { rest, link } };
    const ready = { state: 'ready', caseId: CASE, documents: [], fields: [] };
    rerender(detail, ready, {
      live: true,
      action: 0,
      caseId: null,
      processing: null,
      onProgress() {},
    });
    link.changed = () => {
      changes += 1;
    };
    link.open(OTHER);
    await tick();
    assert.equal(requests.at(-1).path, `/cases/${OTHER}`);
    assert.equal(changes, 1, 'a case the list may not show yet reloads it');
  });

  test('the list waits while the detail view is busy', () => {
    const link = { open() {}, changed() {} };
    rerender({ type: CasePane, props: { rest: async () => ({}), link } }, { state: 'busy' });
    link.open(CASE);
    assert.equal(hooks.states[0].updates.length, 0);
  });

  test('the list loads, refreshes, and drops a late or stale answer', async () => {
    const { rest, requests } = backend();
    const link = { open() {}, changed() {} };
    const list = rerender({ type: CaseListView, props: { rest, link } });
    assert.equal(list.props['aria-label'], 'Case list');
    assert.equal(list.props.children[1].props.children, 'Loading cases…');
    await tick();
    assert.deepEqual(hooks.states[0].updates.at(-1), {
      state: 'ok',
      cases: casesOf(listBody),
    });
    list.props.children[2].props.onClick(); // Refresh list
    link.changed();
    await tick();
    assert.equal(requests.filter((r) => r.path === '/cases').length, 3);
    assert.equal(hooks.states[0].updates.length, 2, 'only the last of two reads lands');
    runCleanups();
    link.changed();
    await tick();
    assert.equal(hooks.states[0].updates.length, 2, 'nothing lands after unmount');
  });

  test('an empty list says how to start', () => {
    const list = rerender(
      { type: CaseListView, props: { rest: async () => ({}), link: { open() {}, changed() {} } } },
      { state: 'ok', cases: [] },
    );
    assert.match(list.props.children[1].props.children, /^No cases yet/);
    assert.equal(list.props.children[2].props.children, 'Refresh list');
  });

  test('case rows are read defensively and hold no case content', () => {
    assert.equal(casesOf(null), null);
    assert.equal(casesOf({ ok: true, cases: 'x' }), null);
    assert.equal(casesOf({ ok: false, cases: [] }), null);
    assert.deepEqual(
      casesOf({
        ok: true,
        cases: [
          null,
          { case_id: CASE },
          {
            case_id: CASE,
            opened_at: '2026-10-30T12:00:00Z',
            outcome: 'toString',
            documents: -1,
            calls: 'two',
            diagnosed: true,
            purged_at: '2026-11-01T00:00:00Z',
            closed_at: '2026-10-31T00:00:00Z',
            payer: 'ACME',
          },
          { case_id: OTHER, opened_at: '2026-10-30T12:00:00Z', extracted: true, outcome: 'upheld' },
        ],
      }),
      [
        {
          caseId: CASE,
          openedOn: '2026-10-30',
          step: 'diagnosed',
          closed: true,
          purged: true,
          outcome: null,
          documents: 0,
          calls: 0,
        },
        {
          caseId: OTHER,
          openedOn: '2026-10-30',
          step: 'extracted',
          closed: false,
          purged: false,
          outcome: 'upheld',
          documents: 0,
          calls: 0,
        },
      ],
    );
    const [purged, upheld] = casesOf({
      ok: true,
      cases: [
        { case_id: CASE, opened_at: '2026-10-30', purged_at: 'x', closed_at: 'y' },
        { case_id: OTHER, opened_at: '2026-10-30', outcome: 'upheld' },
      ],
    });
    assert.match(describeCaseRow(purged), /New · 0 document\(s\) · content purged$/);
    assert.match(describeCaseRow(upheld), /· Upheld$/);
  });
});

describe('US-10.1 the dashboard route is registered', () => {
  test('test_us_10_1_dashboard_route_registered', () => {
    const ctx = createFakeCtx();
    plugin.register(ctx);
    const areas = byArea(ctx.recorded);
    const routes = Object.entries(areas).filter(([area]) => area.startsWith('routes'));
    assert.equal(routes.length, 1);
    const [route] = routes[0][1];
    assert.equal(route.id, 'dashboard');
    assert.deepEqual(route.data, { path: DASHBOARD_PATH });
    assert.equal(route.render().type, DashboardPage);
    const nav = Object.values(areas)
      .flat()
      .find((c) => c.id === 'nav');
    assert.equal(nav.data.path, DASHBOARD_PATH, 'the sidebar entry opens the route');
  });
});

describe('US-10.1 backend errors render as an error state', () => {
  test('test_us_10_1_backend_errors_render_error_state', async () => {
    const rest = async () => {
      throw rejection(503, 'worker_unavailable');
    };
    const pane = rerender({ type: ClaimCoachPane, props: { rest } });
    const [listElement] = pane.props.children;
    assert.doesNotThrow(() => rerender(listElement));
    await tick();
    const failed = hooks.states[0].updates.at(-1);
    assert.deepEqual(failed, { state: 'unavailable' });
    const shown = rerender(listElement, failed);
    const [, error, retry] = shown.props.children;
    assert.equal(error.props.role, 'alert');
    assert.equal(error.props.children, CASE_LIST_UNAVAILABLE);
    assert.doesNotMatch(JSON.stringify(shown.props), /secret text/, 'envelope text is never shown');
    assert.equal(retry.props.children, 'Retry');
    assert.deepEqual(await loadCaseList(createCaseApi(async () => ({ ok: false }))), {
      state: 'unavailable',
    });
  });
});

describe('US-10.2 local-only statusbar indicator', () => {
  test('test_us_10_2_indicator_local_only_default', async () => {
    const ctx = createFakeCtx({
      rest: async () => ({ ok: true, richer_agent_access: false }),
    });
    plugin.register(ctx);
    const [item] = byArea(ctx.recorded)['statusbar.right'];
    const first = item.render().type(item.render().props);
    assert.equal(first.props['data-state'], 'local-only', 'local-only before any answer');
    assert.equal(first.props.children, 'Local-only');
    await tick();
    assert.deepEqual(hooks.states[0].updates, ['local-only']);
    assert.equal(await loadIndicatorState(async () => ({ ok: true })), 'local-only');
    assert.equal(
      await loadIndicatorState(async () => {
        throw new Error('down');
      }),
      'local-only',
      'a failed read is local-only',
    );
    assert.equal(
      await loadIndicatorState(async () => ({ ok: true, richer_agent_access: true })),
      'richer-access',
    );
  });

  test('every indicator state names local models', () => {
    for (const state of ['local-only', 'richer-access']) {
      assert.match(indicatorView(state).title, /local models only/);
    }
    const shown = LocalOnlyIndicator({ rest: async () => ({}) });
    assert.equal(shown.props['data-state'], 'local-only');
  });
});

describe('US-10.3 settings page', () => {
  test('a first read that answers after a save does not undo it', async () => {
    let answer;
    const rest = (path) =>
      path === '/settings'
        ? new Promise((resolve) => {
            answer = resolve;
          })
        : Promise.resolve({ ok: true, retention_days: 30 });
    const page = { type: SettingsPage, props: { rest } };
    const typed = rerender(
      page,
      { state: 'loading' },
      { state: 'loading' },
      { state: 'ok', days: 90 },
      '30',
    );
    typed.props.children[4].props.onSave();
    await tick();
    answer({ ok: true, retention_days: 90 });
    await tick();
    assert.deepEqual(hooks.states[2].updates, [{ state: 'ok', days: 30 }]);
  });

  test('test_us_10_3_settings_registers_when_supported', async () => {
    const ctx = createFakeCtx();
    plugin.register(ctx);
    const [page] = ctx.recorded.settingsPages;
    assert.deepEqual([page.id, page.title, page.icon], ['settings', 'ClaimCoach', 'gear']);
    const rendered = page.render().type(page.render().props);
    const labels = rendered.props.children.slice(2).map((section) => {
      const shown = typeof section.type === 'function' ? section.type(section.props) : section;
      return shown.props['aria-label'];
    });
    assert.deepEqual(labels, ['Models', 'Corpus', 'Retention', 'Global corpus import']);
  });

  test('test_us_10_3_settings_degrade_when_unsupported', () => {
    const ctx = createFakeCtx({ settingsPages: false });
    assert.doesNotThrow(() => plugin.register(ctx));
    assert.equal(ctx.recorded.settingsPages.length, 0);
    assert.ok(byArea(ctx.recorded).panes.length === 1, 'everything else still registers');
  });

  test('test_us_10_3_pane_retention_saved', async () => {
    let stored = 90;
    const requests = [];
    const rest = async (path, opts) => {
      requests.push({ path, opts });
      if (path === '/settings/retention') {
        stored = opts.body.retention_days;
        return { ok: true, richer_agent_access: false, retention_days: stored };
      }
      if (path === '/settings')
        return { ok: true, richer_agent_access: false, retention_days: stored };
      throw rejection(503, 'worker_unavailable');
    };
    const page = { type: SettingsPage, props: { rest } };
    rerender(page);
    await tick();
    const [models, corpus, retention] = [1, 2, 3].map((i) => hooks.states[i - 1].updates.at(-1));
    assert.deepEqual([models, corpus], [{ state: 'unavailable' }, { state: 'unavailable' }]);
    assert.deepEqual(retention, { state: 'ok', days: 90 }, 'retention loads without the worker');

    const typed = rerender(page, models, corpus, retention, '30', null, {
      live: true,
      saved: false,
    });
    const section = typed.props.children[4];
    const shown = section.type(section.props);
    const [, status, input, save] = shown.props.children;
    assert.match(status.props.children, /for 90 days/);
    assert.equal(input.props.value, '30');
    assert.equal(save.props.disabled, false);
    save.props.onClick();
    assert.deepEqual(hooks.states[4].updates, [{ state: 'saving' }]);
    await tick();
    assert.deepEqual(requests.at(-1), {
      path: '/settings/retention',
      opts: { method: 'POST', body: { retention_days: 30 } },
    });
    assert.deepEqual(hooks.states[4].updates.at(-1), { state: 'saved', days: 30 });
    assert.deepEqual(hooks.states[2].updates.at(-1), { state: 'ok', days: 30 });
    assert.deepEqual(hooks.states[3].updates.at(-1), null, 'the editor shows the stored value');
    assert.match(describeSave({ state: 'saved', days: 30 }), /more than 30 days ago/);
  });

  test('saving waits for a valid, changed value and drops a late answer', async () => {
    const rest = async () => ({ ok: true, retention_days: 90 });
    const page = { type: SettingsPage, props: { rest } };
    const retention = { state: 'ok', days: 90 };
    for (const draft of [null, 'abc', '0']) {
      const typed = rerender(page, { state: 'loading' }, { state: 'loading' }, retention, draft);
      typed.props.children[4].props.onSave();
      assert.equal(hooks.states[4].updates.length, 0, String(draft));
    }
    const busy = rerender(page, { state: 'loading' }, { state: 'loading' }, retention, '30', {
      state: 'saving',
    });
    busy.props.children[4].props.onSave();
    assert.equal(hooks.states[4].updates.length, 0, 'one save at a time');

    const late = rerender(page, { state: 'loading' }, { state: 'loading' }, retention, '30', null);
    late.props.children[4].props.onSave();
    runCleanups();
    await tick();
    assert.deepEqual(hooks.states[4].updates, [{ state: 'saving' }], 'nothing lands after unmount');
    assert.deepEqual(hooks.states[0].updates, [], 'loads after unmount are dropped');
  });

  test('a refused save keeps the typed value', async () => {
    const rest = async (path) => {
      if (path === '/settings/retention') throw rejection(403, 'settings_managed');
      return { ok: true, retention_days: 90 };
    };
    const page = { type: SettingsPage, props: { rest } };
    const typed = rerender(
      page,
      { state: 'loading' },
      { state: 'loading' },
      { state: 'ok', days: 90 },
      '30',
    );
    typed.props.children[4].props.onSave();
    await tick();
    assert.deepEqual(hooks.states[4].updates.at(-1), {
      state: 'refused',
      code: 'settings_managed',
    });
    assert.equal(hooks.states[3].updates.length, 0, 'the draft stays');
  });

  test('saveRetention and describeSave cover every answer', async () => {
    assert.deepEqual(await saveRetention(async () => ({ ok: true }), 30), { state: 'failed' });
    assert.deepEqual(
      await saveRetention(async () => {
        throw new Error('offline');
      }, 30),
      { state: 'failed' },
    );
    assert.deepEqual(
      await saveRetention(async () => {
        throw rejection(422, 'invalid_request');
      }, 30),
      { state: 'refused', code: 'invalid_request' },
    );
    assert.equal(describeSave({ state: 'saving' }), 'Saving…');
    for (const code of Object.keys(SETTINGS_REFUSALS)) {
      assert.equal(describeSave({ state: 'refused', code }), SETTINGS_REFUSALS[code]);
    }
    assert.equal(
      describeSave({ state: 'refused', code: 'other' }),
      'The retention period was not saved.',
    );
    assert.match(describeSave({ state: 'failed' }), /not saved/);
  });

  test('parseDays accepts whole days from 1 to 3650 only', () => {
    assert.equal(parseDays(' 30 '), 30);
    assert.equal(parseDays('3650'), 3650);
    for (const text of ['', '0', '3651', '1.5', '-3', '1e3', '12345']) {
      assert.equal(parseDays(text), null, text);
    }
  });

  test('the retention section before the period loads', () => {
    const loading = RetentionSection({
      retention: { state: 'loading' },
      draft: null,
      result: null,
      onDraft() {},
      onSave() {},
    });
    const [, status, input, save, , result] = loading.props.children;
    assert.equal(status.props.children, 'Loading the retention period…');
    assert.equal(input.props.value, '');
    assert.equal(input.props.disabled, true);
    assert.equal(save.props.disabled, true);
    assert.equal(result, null);
    const drafts = [];
    const unavailable = RetentionSection({
      retention: { state: 'unavailable' },
      draft: null,
      result: { state: 'failed' },
      onDraft: (text) => drafts.push(text),
      onSave() {},
    });
    assert.match(unavailable.props.children[1].props.children, /^Unavailable/);
    assert.match(unavailable.props.children[5].props.children, /not saved/);
    unavailable.props.children[2].props.onChange({ currentTarget: { value: '45' } });
    assert.deepEqual(drafts, ['45']);
    const same = RetentionSection({
      retention: { state: 'ok', days: 90 },
      draft: '90',
      result: null,
      onDraft() {},
      onSave() {},
    });
    assert.equal(same.props.children[3].props.disabled, true, 'nothing to save');
    const stored = RetentionSection({
      retention: { state: 'ok', days: 90 },
      draft: null,
      result: null,
      onDraft() {},
      onSave() {},
    });
    assert.equal(
      stored.props.children[2].props.value,
      '90',
      'the editor starts at the stored value',
    );
  });

  test('model and corpus sections show status or a fixed error', async () => {
    const status = {
      ok: true,
      models: [
        { role: 'classification', state: 'ready', weights: 'present', venv_present: true },
        { role: 'transcription', state: 'unloaded', weights: 'missing', venv_present: false },
        { role: 7 },
        null,
      ],
    };
    const models = await loadModels(async () => status);
    assert.equal(models.state, 'ok');
    const list = ModelsSection(models).props.children[1];
    assert.deepEqual(
      list.props.children.map((li) => li.props.children),
      [
        'classification: ready · weights present · venv ready',
        'transcription: unloaded · weights missing · venv missing',
      ],
    );
    assert.equal(modelsOf({ ok: true }), null);
    assert.deepEqual(await loadModels(async () => ({ ok: false })), { state: 'unavailable' });
    assert.equal(ModelsSection({ state: 'loading' }).props.children[1].props.role, 'status');
    assert.equal(ModelsSection({ state: 'unavailable' }).props.children[1].props.role, 'alert');

    const scope = (extra) => ({ encrypted: true, cases: 3, documents: 5, ...extra });
    const corpus = await loadCorpus(async () => ({
      ok: true,
      global_scope: scope({ encrypted: false, cases: 'x', documents: 5 }),
      user_scopes: [scope({ profile: 'default' })],
    }));
    const [, global, user] = CorpusSection(corpus).props.children;
    assert.equal(global.props.children, 'Global corpus: 5 document(s).');
    assert.equal(
      user.props.children,
      'Your case store: 3 case(s), 5 document(s), encrypted at rest.',
    );
    const lines = (value) =>
      CorpusSection(value)
        .props.children.slice(1)
        .map((p) => p.props.children);
    assert.deepEqual(
      lines({
        state: 'ok',
        global: { ...corpus.global, available: false },
        user: null,
      }),
      [
        'Global corpus: could not be opened.',
        'Your case store: none yet; it is created with your first case.',
      ],
    );
    assert.deepEqual(
      lines({
        state: 'ok',
        global: corpus.global,
        user: { cases: 0, documents: 0, encrypted: false, available: false },
      })[1],
      'Your case store: could not be opened (its key is missing or wrong).',
    );
    assert.deepEqual(
      lines({ state: 'ok', global: corpus.global, user: { ...corpus.user, encrypted: false } })[1],
      'Your case store: 3 case(s), 5 document(s), not encrypted at rest.',
    );
    assert.equal(corpusOf({ ok: true, global_scope: null }), null);
    assert.equal(
      corpusOf({ ok: true, global_scope: scope({ documents: null }) }).global.documents,
      0,
    );
    assert.deepEqual(corpusOf({ ok: true, global_scope: scope() }).user, null);
    assert.deepEqual(lines({ state: 'loading' }), ['Loading corpus status…']);
    assert.match(lines({ state: 'unavailable' })[0], /^Unavailable/);
    assert.deepEqual(await loadRetention(async () => ({ ok: true, retention_days: 0 })), {
      state: 'unavailable',
    });
  });
});

describe('EPIC-10 review regressions', () => {
  const lifeOf = (caseId = CASE) => ({
    live: true,
    action: 0,
    caseId,
    processing: null,
    onProgress() {},
  });

  test('a case that fails to open stays selected, so the next document goes to it', async () => {
    const link = { open() {}, changed() {}, drop() {} };
    const rest = async () => {
      throw rejection(503, 'worker_unavailable');
    };
    const ready = { state: 'ready', caseId: CASE, documents: [], fields: [] };
    rerender({ type: CasePane, props: { rest, link } }, ready, lifeOf());
    link.open(OTHER);
    await tick();
    assert.deepEqual(hooks.states[0].updates.at(-1), { state: 'unavailable', caseId: OTHER });
    assert.equal(hooks.states[1].value.caseId, OTHER, 'the pane now works on the selected case');
  });

  test('opening another case waits for unsaved draft edits', () => {
    const requests = [];
    const link = { open() {}, changed() {}, drop() {} };
    const ready = {
      state: 'ready',
      caseId: CASE,
      documents: [],
      fields: [],
      draft: {
        text: 'Stored letter.',
        templateId: 't',
        ruleCards: [],
        stale: false,
        edited: false,
      },
    };
    const rest = async (path) => {
      requests.push(path);
      return {};
    };
    rerender({ type: CasePane, props: { rest, link } }, ready, lifeOf(), '', {}, 'Unsaved letter.');
    link.open(OTHER);
    assert.deepEqual(requests, []);
    const shown = hooks.states[0].updates.at(-1);
    assert.equal(shown.notice, 'unsaved_draft');
    assert.equal(shown.caseId, CASE);
    assert.deepEqual(hooks.states[4].updates, [], 'the editor keeps the text');
  });

  test('a file dropped anywhere on the pane joins the open case', () => {
    const pane = rerender({ type: ClaimCoachPane, props: { rest: async () => ({}) } });
    const { link } = pane.props.children[0].props;
    const dropped = [];
    link.drop = (files) => dropped.push(files);
    let prevented = 0;
    const event = (files) => ({
      preventDefault: () => {
        prevented += 1;
      },
      dataTransfer: files ? { files } : null,
    });
    pane.props.onDragOver(event());
    pane.props.onDrop(event([{ name: 'eob.pdf' }]));
    pane.props.onDrop(event(null));
    assert.equal(prevented, 3, 'the webview never opens a dropped file');
    assert.deepEqual(dropped, [[{ name: 'eob.pdf' }], undefined]);

    const detail = rerender(pane.props.children[1]);
    assert.notEqual(link.drop, undefined);
    let stopped = 0;
    detail.props.onDrop({
      preventDefault() {},
      stopPropagation: () => {
        stopped += 1;
      },
      dataTransfer: { files: [] },
    });
    assert.equal(stopped, 1, 'a drop on the detail view is not added twice');
    link.drop([]); // the detail view's handler: nothing to add
    assert.equal(hooks.states[0].updates.length, 0);
  });

  test('case rows show the open date on this Mac', () => {
    const [row] = casesOf({ ok: true, cases: [{ case_id: CASE, opened_at: 'not a date at all' }] });
    assert.equal(row.openedOn, 'not a date');
    const noon = new Date(2026, 9, 30, 12).toISOString();
    assert.equal(
      casesOf({ ok: true, cases: [{ case_id: CASE, opened_at: noon }] })[0].openedOn,
      '2026-10-30',
    );
  });

  test('an invalid stored period says purges are skipped and takes a new one', async () => {
    assert.deepEqual(await loadRetention(async () => ({ ok: true, retention_days: null })), {
      state: 'invalid',
    });
    const drafts = [];
    const section = RetentionSection({
      retention: { state: 'invalid' },
      draft: null,
      result: null,
      onDraft: (text) => drafts.push(text),
      onSave() {},
    });
    const [, status, input, save] = section.props.children;
    assert.match(status.props.children, /invalid, so no closed case is purged/);
    assert.equal(input.props.disabled, false);
    assert.equal(save.props.disabled, true, 'nothing typed yet');
    const typed = RetentionSection({
      retention: { state: 'invalid' },
      draft: '30',
      result: null,
      onDraft() {},
      onSave() {},
    });
    assert.equal(typed.props.children[3].props.disabled, false);
  });

  test('the detail view also renders under a rejecting backend', () => {
    const rest = async () => {
      throw rejection(503, 'worker_unavailable');
    };
    const pane = rerender({ type: ClaimCoachPane, props: { rest } });
    assert.doesNotThrow(() => rerender(pane.props.children[1]));
  });
});
