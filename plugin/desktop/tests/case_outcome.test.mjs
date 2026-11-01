/**
 * node --test suite for the case outcome in the pane. US-8.1 scenarios:
 *   - Outcome is recorded on the case (after the biller confirms that it closes the case)
 *   - A later outcome corrects the first
 *   - An outcome while a job runs
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  createCaseApi,
  describeCase,
  OUTCOMES,
  OutcomePanel,
  openCase,
  outcomeOf,
  REFUSALS,
  recordOutcome,
} from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const at = {
  upload: 2,
  process: 4,
  newCase: 5,
  paste: 6,
  attach: 7,
  fields: 10,
  diagnose: 11,
  draftButton: 14,
  draftPanel: 15,
  outcomePanel: 16,
};
const slot = { current: 0, pending: 6 };
const RECORDED = '2026-10-31T15:04:05Z';
const DRAFT = {
  label: 'draft for human review',
  text: 'Re: Appeal of claim CLAIM-77',
  template_id: 'appeal',
  rule_cards: [],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
  drafted_at: '2026-10-31T12:05:00Z',
  edited_at: null,
};

/** A case body as `GET /cases/{id}` returns it. */
function caseBody({ outcome = null, closed = null, draft = null } = {}) {
  return {
    ok: true,
    case_id: CASE,
    opened_at: '2026-10-30T10:00:00Z',
    closed_at: closed,
    documents: [{ doc_id: 'src_0', kind: 'edi_835', filename: null }],
    extraction: null,
    needs_confirmation: [],
    diagnosis: null,
    draft,
    outcome: outcome === null ? null : { case_id: CASE, outcome, recorded_at: RECORDED },
  };
}

/** A Hermes `ctx.rest` rejection carrying an envelope code. */
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

/** A worker that records outcomes as plugin_api does: the first one closes the case. */
function backend() {
  const state = { body: caseBody(), requests: [] };
  const rest = async (path, opts) => {
    state.requests.push({ path, method: opts?.method ?? 'GET', body: opts?.body });
    if (path === `/cases/${CASE}/outcome`) {
      state.body = caseBody({ outcome: opts.body.outcome, closed: RECORDED });
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

function mounted(rest) {
  const ctx = createFakeCtx({ rest, events: true });
  plugin.register(ctx);
  return { ctx, element: byArea(ctx.recorded).panes[0].render() };
}

const panelOf = (pane) => {
  const element = pane.props.children[at.outcomePanel];
  return element.type(element.props);
};
const latest = (index = slot.current) => hooks.states[index].updates.at(-1);
const buttons = (panel) => panel.props.children.filter((c) => c?.type === 'button');
const button = (panel, label) => buttons(panel).find((c) => c.props.children === label);

afterEach(() => runCleanups());

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-8.1 outcome is recorded on the case', () => {
  test('test_us_8_1_pane_outcome_recorded', async () => {
    const { rest, state } = backend();
    const { element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    assert.equal(ready.outcome, undefined);
    assert.equal(ready.closed, undefined);
    const panel = panelOf(rerender(element, ready, life()));
    assert.equal(panel.props['aria-label'], 'Case outcome');
    const [heading, status, closed] = panel.props.children;
    assert.equal(heading.props.children, 'Outcome');
    assert.equal(status.props.children, 'No outcome recorded yet. Marking one closes the case.');
    assert.equal(closed, null);
    assert.deepEqual(
      buttons(panel).map((b) => [b.props.children, b.props.disabled]),
      [
        ['Mark overturned', false],
        ['Mark upheld', false],
        ['Mark written off', false],
      ],
    );

    button(panel, 'Mark overturned').props.onClick();
    await tick();
    assert.equal(state.requests.length, 1, 'nothing is recorded before the biller confirms');
    assert.equal(latest(slot.pending), 'overturned');
    const asking = panelOf(rerender(element, ready, life(), '', {}, null, null, 'overturned'));
    const dialog = asking.props.children.at(-1);
    assert.equal(dialog.props.role, 'alertdialog');
    assert.match(
      dialog.props.children[0].props.children,
      /^Mark the case overturned\? This closes/,
    );
    assert.ok(
      buttons(asking).every((b) => b.props.disabled),
      'one choice at a time',
    );
    dialog.props.children[2].props.onClick(); // Cancel
    assert.equal(latest(slot.pending), null);
    assert.equal(state.requests.length, 1, 'cancel records nothing');

    const again = panelOf(rerender(element, ready, life(), '', {}, null, null, 'overturned'));
    const confirm = again.props.children.at(-1).props.children[1];
    assert.equal(confirm.props.children, 'Close the case');
    confirm.props.onClick();
    assert.equal(latest(slot.pending), null);
    await tick();
    assert.deepEqual(state.requests.at(-1), {
      path: `/cases/${CASE}/outcome`,
      method: 'POST',
      body: { outcome: 'overturned' },
    });
    const recorded = latest();
    assert.equal(recorded.state, 'ready');
    assert.deepEqual(recorded.outcome, { outcome: 'overturned', recordedAt: RECORDED });
    assert.equal(recorded.closed, true, 'recording the outcome closes the case');

    const shown = panelOf(rerender(element, recorded, life()));
    const [, line, closedLine] = shown.props.children;
    assert.equal(line.props.children, 'Outcome: Overturned (recorded 2026-10-31).');
    assert.equal(closedLine.props.children, 'Case closed.');
    assert.equal(button(shown, 'Mark overturned').props.disabled, true, 'already recorded');
    assert.deepEqual(hostAccesses, []);
  });

  test('a closed case keeps only Refresh, New case, the exports, and the outcome', async () => {
    const body = caseBody({ outcome: 'upheld', closed: RECORDED, draft: DRAFT });
    const closed = await openCase(
      createCaseApi(async () => body),
      CASE,
    );
    const pane = rerender({ type: CasePane, props: { rest: async () => body } }, closed, life());
    for (const name of ['upload', 'process', 'paste', 'attach', 'diagnose', 'draftButton']) {
      assert.equal(pane.props.children[at[name]].props.disabled, true, name);
    }
    assert.equal(pane.props.children[at.fields].props.disabled, true);
    assert.equal(pane.props.children[at.newCase].props.disabled, false);
    const draft = pane.props.children[at.draftPanel];
    const panel = draft.type(draft.props);
    const [, , , editor, save, pdf, docx] = panel.props.children;
    assert.deepEqual(
      [editor.props.disabled, save.props.disabled, pdf.props.disabled, docx.props.disabled],
      [true, true, false, false],
      'a closed case still exports',
    );
    assert.match(
      describeCase(closed),
      /This case is closed; start a new case for more documents\.$/,
    );
    pane.props.onDrop({ preventDefault() {}, dataTransfer: { files: [{ name: 'x.pdf' }] } });
    const typed = rerender(
      { type: CasePane, props: { rest: async () => body } },
      closed,
      life(),
      'More',
    );
    typed.props.children[at.attach].props.onClick();
    assert.equal(hooks.states[slot.current].updates.length, 0, 'nothing is added to a closed case');
  });

  test('every outcome has a label and a Mark button', () => {
    assert.deepEqual(Object.keys(OUTCOMES), ['overturned', 'upheld', 'written_off']);
    const panel = OutcomePanel({ outcome: undefined, closed: false, disabled: true, onMark() {} });
    assert.ok(
      buttons(panel).every((b) => b.props.disabled),
      'disabled until a case is ready',
    );
  });

  test('malformed outcomes are not shown', () => {
    assert.equal(outcomeOf(null), null);
    assert.equal(outcomeOf({ outcome: null }), null);
    assert.equal(outcomeOf({ outcome: { outcome: 'won', recorded_at: RECORDED } }), null);
    assert.equal(outcomeOf({ outcome: { outcome: 'toString', recorded_at: RECORDED } }), null);
    assert.equal(outcomeOf({ outcome: { outcome: 'upheld', recorded_at: 7 } }), null);
    assert.deepEqual(outcomeOf({ outcome: { outcome: 'upheld', recorded_at: RECORDED } }), {
      outcome: 'upheld',
      recordedAt: RECORDED,
    });
  });

  test('the Mark buttons wait for a ready case and for unsaved editor text', async () => {
    const idle = rerender({ type: CasePane, props: { rest: async () => ({}) } });
    const idlePanel = panelOf(idle);
    assert.ok(buttons(idlePanel).every((b) => b.props.disabled));
    buttons(idlePanel).at(-1).props.onClick(); // a stray click before a case is open
    idle.props.children[at.outcomePanel].props.onConfirm(); // nothing chosen
    const stray = rerender(
      { type: CasePane, props: { rest: async () => ({}) } },
      { state: 'idle' },
      life(null),
      '',
      {},
      null,
      null,
      'upheld',
    );
    stray.props.children[at.outcomePanel].props.onConfirm(); // no case open
    assert.equal(hooks.states[slot.current].updates.length, 0, 'nothing happens');

    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const pane = { type: CasePane, props: { rest: async () => ({}) } };
    const dirty = rerender(pane, ready, life(), '', {}, 'Unsaved letter.', null);
    assert.ok(
      buttons(panelOf(dirty)).every((b) => b.props.disabled),
      'save the draft first',
    );
    const clean = rerender(pane, ready, life(), '', {}, null, null);
    assert.ok(buttons(panelOf(clean)).every((b) => !b.props.disabled));
  });
});

describe('US-8.1 a later outcome corrects the first', () => {
  test('test_us_8_1_pane_outcome_corrected', async () => {
    const { rest, state } = backend();
    state.body = caseBody({ outcome: 'upheld', closed: RECORDED });
    const { element } = mounted(rest);
    const closed = await openCase(createCaseApi(rest), CASE);
    assert.equal(closed.closed, true);
    const panel = panelOf(rerender(element, closed, life()));
    assert.equal(button(panel, 'Mark upheld').props.disabled, true);
    button(panel, 'Mark written off').props.onClick();
    await tick();
    assert.deepEqual(state.requests.at(-1).body, { outcome: 'written_off' });
    assert.deepEqual(latest().outcome, { outcome: 'written_off', recordedAt: RECORDED });
  });
});

describe('US-8.1 an outcome while a job runs', () => {
  test('test_us_8_1_pane_outcome_refused_while_a_job_runs', async () => {
    const api = createCaseApi(async (path) => {
      if (path.endsWith('/outcome')) throw rejection(409, 'model_busy');
      return caseBody();
    });
    const refused = await recordOutcome(api, CASE, 'upheld');
    assert.equal(refused.state, 'ready');
    assert.equal(refused.notice, 'outcome_busy');
    assert.equal(refused.outcome, undefined);
    assert.ok(describeCase(refused).startsWith(REFUSALS.outcome_busy));
  });

  test('other refusals and failures', async () => {
    const closedApi = createCaseApi(async (path) => {
      if (path.endsWith('/outcome')) throw rejection(409, 'case_closed');
      return caseBody();
    });
    assert.equal((await recordOutcome(closedApi, CASE, 'upheld')).notice, 'case_closed');
    for (const failure of [rejection(500, 'internal_error'), new Error('offline')]) {
      const api = createCaseApi(async () => {
        throw failure;
      });
      assert.deepEqual(await recordOutcome(api, CASE, 'upheld'), { state: 'unavailable' });
    }
    const other = createCaseApi(async () => ({ ...caseBody(), case_id: 'case_other' }));
    assert.deepEqual(await recordOutcome(other, CASE, 'upheld'), { state: 'unavailable' });
  });
});
