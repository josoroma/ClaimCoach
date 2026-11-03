/**
 * node --test suite for the manager dashboard. US-8.2 scenario:
 *   - Only opted-in profiles are aggregated (the dashboard shows which profiles were read)
 * US-8.3 scenario:
 *   - Export requires manager approval
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  DashboardPage,
  describeCounts,
  describeFineTune,
  describeSharing,
  exportFineTune,
  FineTunePanel,
  loadSummary,
  summaryOf,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const slot = { loaded: 0, manager: 1, approved: 2, fineTune: 3 };
const PATH = '/Users/manager/.hermes/plugin-data/claimcoach/fine-tune/fine-tune-1.jsonl';
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

const counts = (overturned, upheld, writtenOff) => {
  const total = overturned + upheld + writtenOff;
  return {
    overturned,
    upheld,
    written_off: writtenOff,
    total,
    overturn_rate: total ? Math.round((overturned / total) * 10_000) / 10_000 : null,
  };
};

const SUMMARY = {
  ok: true,
  week: '2026-W43',
  starts_at: '2026-10-19T04:00:00Z',
  ends_at: '2026-10-26T04:00:00Z',
  timezone: 'America/New_York',
  profiles: ['default'],
  not_shared: 1,
  unreadable: [],
  totals: counts(2, 1, 0),
  by_category: [
    { payer: 'ACME Health', denial_reason: 'prior_authorization', ...counts(2, 0, 0) },
    { payer: null, denial_reason: null, ...counts(0, 1, 0) },
  ],
  by_code: [
    { payer: 'ACME Health', code: 'CO-197', ...counts(2, 0, 0) },
    { payer: null, code: 'N286', ...counts(0, 1, 0) },
  ],
};

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

describe('US-8.2 only opted-in profiles are aggregated', () => {
  test('test_us_8_2_dashboard_shows_the_weekly_summary', async () => {
    const calls = [];
    const ctx = createFakeCtx({
      rest: async (path) => {
        calls.push(path);
        return SUMMARY;
      },
    });
    plugin.register(ctx);
    const route = byArea(ctx.recorded).routes[0];
    const element = route.render();
    const loading = rerender(element);
    assert.equal(loading.props.children[1].props.children, 'Loading the weekly outcome summary…');
    await tick();
    assert.deepEqual(calls, ['/outcomes/summary']);
    const loaded = hooks.states[0].updates.at(-1);
    assert.equal(loaded.state, 'ok');

    const page = rerender(element, loaded);
    const [, week, sharing, totals, list, codeList] = page.props.children;
    assert.equal(week.props.children, 'Week 2026-W43 (America/New_York)');
    assert.equal(
      sharing.props.children,
      'Profiles sharing their outcomes: default. 1 profile(s) do not share theirs.',
    );
    assert.equal(
      totals.props.children,
      'All payers: 3 outcome(s): 2 overturned, 1 upheld, 0 written off (67% overturned).',
    );
    assert.deepEqual(
      list.props.children.map((item) => item.props.children),
      [
        'ACME Health · Prior authorization or referral: 2 outcome(s): 2 overturned, 0 upheld, ' +
          '0 written off (100% overturned).',
        'Payer without rule cards · Not diagnosed: 1 outcome(s): 0 overturned, 1 upheld, ' +
          '0 written off (0% overturned).',
      ],
    );
    assert.equal(codeList.props['aria-label'], 'Outcomes per payer and code');
    assert.deepEqual(
      codeList.props.children.map((item) => item.props.children),
      [
        'ACME Health · CO-197: 2 outcome(s): 2 overturned, 0 upheld, 0 written off ' +
          '(100% overturned).',
        'Payer without rule cards · N286: 1 outcome(s): 0 overturned, 1 upheld, 0 written off ' +
          '(0% overturned).',
      ],
    );
    assert.deepEqual(hostAccesses, []);
  });

  test('an unavailable summary, and an answer after unmount', async () => {
    for (const rest of [
      async () => {
        throw new Error('503: {}');
      },
      async () => ({ ok: true }),
    ]) {
      assert.deepEqual(await loadSummary(rest), { state: 'unavailable' });
    }
    const page = rerender(
      { type: DashboardPage, props: { rest: async () => ({}) } },
      {
        state: 'unavailable',
      },
    );
    assert.match(page.props.children[1].props.children, /unavailable; check that the ClaimCoach/);
    let release;
    const slow = rerender({
      type: DashboardPage,
      props: { rest: () => new Promise((resolve) => (release = resolve)) },
    });
    assert.equal(slow.props['aria-label'], 'ClaimCoach manager dashboard');
    runCleanups(); // unmounted before the answer
    release(SUMMARY);
    await tick();
    assert.equal(hooks.states[0].updates.length, 0, 'a late answer is dropped');
  });

  test('sharing lines and malformed summaries', () => {
    const none = summaryOf({ ...SUMMARY, profiles: [], not_shared: 0, unreadable: ['b'] });
    assert.equal(
      describeSharing(none),
      'No profile shares its outcomes yet (Settings → Plugins → ClaimCoach). ' +
        '1 profile(s) could not be read this time.',
    );
    assert.equal(
      describeCounts({ overturned: 0, upheld: 0, writtenOff: 0, total: 0, rate: null }),
      '0 outcome(s): 0 overturned, 0 upheld, 0 written off.',
    );
    assert.equal(summaryOf(null), null);
    assert.equal(summaryOf({ ...SUMMARY, week: 7 }), null);
    assert.equal(summaryOf({ ...SUMMARY, timezone: null }), null);
    assert.equal(summaryOf({ ...SUMMARY, not_shared: -1 }), null);
    assert.equal(summaryOf({ ...SUMMARY, totals: { ...SUMMARY.totals, upheld: 1.5 } }), null);
    for (const field of ['overturned', 'written_off', 'total']) {
      assert.equal(summaryOf({ ...SUMMARY, totals: { ...SUMMARY.totals, [field]: '1' } }), null);
    }
    const rows = summaryOf({
      ...SUMMARY,
      profiles: 'default',
      unreadable: null,
      totals: { ...SUMMARY.totals, overturn_rate: null },
      by_category: [
        { payer: 'ACME Health', denial_reason: 'toString', ...counts(1, 0, 0) },
        { payer: 'ACME Health', denial_reason: 'bundling', upheld: 'x' },
        { payer: 7, denial_reason: 'bundling', ...counts(0, 0, 1) },
        null,
      ],
    });
    assert.deepEqual(rows.profiles, []);
    assert.equal(rows.unreadable, 0);
    assert.equal(rows.totals.rate, null);
    assert.deepEqual(rows.categories, [
      {
        overturned: 0,
        upheld: 0,
        writtenOff: 1,
        total: 1,
        rate: 0,
        payer: null,
        reason: 'bundling',
      },
    ]);
    assert.deepEqual(summaryOf({ ...SUMMARY, by_category: 'x' }).categories, []);
    const codes = summaryOf({
      ...SUMMARY,
      by_code: [
        { payer: 7, code: 'CO-197', ...counts(1, 0, 0) },
        { payer: 'ACME Health', code: 7, ...counts(1, 0, 0) },
        { payer: 'ACME Health', code: 'CO-197', upheld: 'x' },
      ],
    }).codes;
    assert.deepEqual(codes, [
      { overturned: 1, upheld: 0, writtenOff: 0, total: 1, rate: 1, payer: null, code: 'CO-197' },
    ]);
    assert.deepEqual(summaryOf({ ...SUMMARY, by_code: null }).codes, []);
  });
});

describe('US-8.3 export requires manager approval', () => {
  const ok = { state: 'ok', summary: summaryOf(SUMMARY) };
  const page = (rest) => ({ type: DashboardPage, props: { rest } });
  const panelOf = (rendered) => {
    const element = rendered.props.children.find((child) => child.type === FineTunePanel);
    return element.type(element.props);
  };
  const exportButton = (panel) => panel.props.children[4];

  test('test_us_8_3_pane_export_requires_approval', async () => {
    const requests = [];
    const rest = async (path, opts) => {
      requests.push({ path, opts });
      return path === '/outcomes/export'
        ? { ok: true, path: PATH, filename: 'fine-tune-1.jsonl', records: 2 }
        : SUMMARY;
    };
    const fresh = panelOf(rerender(page(rest), ok));
    assert.equal(fresh.props['aria-label'], 'Fine-tune export');
    assert.equal(exportButton(fresh).props.disabled, true, 'no name, no approval');
    const named = panelOf(rerender(page(rest), ok, 'Dana Manager', false));
    assert.equal(exportButton(named).props.disabled, true, 'a name is not an approval');
    exportButton(named).props.onClick();
    const unticked = panelOf(rerender(page(rest), ok, '   ', true));
    assert.equal(exportButton(unticked).props.disabled, true, 'an approval needs a name');
    exportButton(unticked).props.onClick();
    await tick();
    assert.deepEqual(
      requests.map((r) => r.path),
      ['/outcomes/summary', '/outcomes/summary', '/outcomes/summary'],
      'nothing is exported without both',
    );

    const ready = panelOf(rerender(page(rest), ok, ' Dana Manager ', true));
    const [, , nameInput, checkbox] = ready.props.children;
    nameInput.props.onChange({ currentTarget: { value: 'Dana' } });
    assert.equal(hooks.states[slot.manager].updates.at(-1), 'Dana');
    checkbox.props.onChange({ currentTarget: { checked: false } });
    assert.equal(hooks.states[slot.approved].updates.at(-1), false);
    const button = exportButton(ready);
    assert.equal(button.props.children, 'Export fine-tune set');
    assert.equal(button.props.disabled, false);
    button.props.onClick();
    assert.deepEqual(hooks.states[slot.fineTune].updates.at(-1), { state: 'exporting' });
    assert.equal(hooks.states[slot.approved].updates.at(-1), false, 'each export is approved anew');
    await tick();
    assert.deepEqual(requests.at(-1), {
      path: '/outcomes/export',
      opts: { method: 'POST', body: { approval: { manager: 'Dana Manager', approved: true } } },
    });
    const written = hooks.states[slot.fineTune].updates.at(-1);
    assert.deepEqual(written, { state: 'written', path: PATH, records: 2 });
    const shown = panelOf(rerender(page(rest), ok, 'Dana Manager', false, written));
    assert.equal(
      shown.props.children.at(-1).props.children,
      `2 de-identified pair(s) written to ${PATH}.`,
    );

    const busy = panelOf(rerender(page(rest), ok, 'Dana Manager', true, { state: 'exporting' }));
    assert.equal(exportButton(busy).props.disabled, true, 'one export at a time');
    exportButton(busy).props.onClick();
    assert.equal(hooks.states[slot.fineTune].updates.length, 0);
  });

  test('refusals, failures, and an answer after unmount', async () => {
    for (const [failure, state] of [
      [rejection(403, 'export_not_approved'), 'refused'],
      [rejection(422, 'invalid_request'), 'refused'],
      [rejection(502, 'worker_unavailable'), 'failed'],
      [new Error('offline'), 'failed'],
    ]) {
      const rest = async () => {
        throw failure;
      };
      assert.deepEqual(await exportFineTune(rest, 'Dana Manager'), { state });
    }
    for (const body of [null, { ok: true, path: 7, records: 1 }, { ok: true, path: PATH }]) {
      assert.deepEqual(await exportFineTune(async () => body, 'Dana Manager'), { state: 'failed' });
    }
    assert.equal(describeFineTune({ state: 'exporting' }), 'Exporting…');
    assert.match(describeFineTune({ state: 'refused' }), /nothing was exported/);
    assert.match(describeFineTune({ state: 'failed' }), /could not be written/);

    let release;
    const rest = (path) =>
      path === '/outcomes/export' ? new Promise((resolve) => (release = resolve)) : SUMMARY;
    const panel = panelOf(rerender(page(rest), ok, 'Dana Manager', true));
    exportButton(panel).props.onClick();
    runCleanups(); // the dashboard closed before the answer
    release({ ok: true, path: PATH, records: 1 });
    await tick();
    assert.deepEqual(hooks.states[slot.fineTune].updates, [{ state: 'exporting' }]);
  });
});
