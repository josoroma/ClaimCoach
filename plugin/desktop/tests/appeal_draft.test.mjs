/**
 * node --test suite for the appeal draft in the pane. US-7.1 scenarios:
 *   - Draft is generated from rule card and template
 *   - Draft carries the human-review label
 * US-7.2 scenarios:
 *   - Edits are saved to the draft
 *   - Export produces PDF
 *   - Export produces DOCX
 *   - The biller chooses where the file is saved
 * US-7.3 scenario:
 *   - No contribution offers send or submit
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  createCaseApi,
  DRAFT_LABEL,
  DraftPanel,
  describeCase,
  describeExport,
  draftButtonLabel,
  draftCase,
  draftOf,
  exportDraft,
  openCase,
  PROGRESS_EVENT,
  REFUSALS,
  saveDraft,
} from '../plugin.js';
import { ABSOLUTE, controlStrings, SEND } from './controls.mjs';
import { byArea, casePaneOf, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses, setFileDownload } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const DRAFT_JOB = 'job_0aaaaaaaaaaaaaaa';
const at = { diagnose: 11, draftButton: 15, draftPanel: 16 };
const slot = { current: 0, life: 1, letter: 4, exported: 5 };
const LETTER = 'Re: Appeal of claim CLAIM-77\n\nTo the appeals reviewer:\n\n[Signature]';
const EXPIRES = '2026-10-31T12:15:00Z';
const PATH = `/Users/biller/.hermes/plugin-data/claimcoach/exports/appeal-draft-${CASE}-0f.pdf`;

const read = (value) => ({ value, status: 'extracted' });

const DIAGNOSIS = {
  denial_reason: 'prior_authorization',
  appeal_likelihood: 'high',
  likelihood_reasons: ['The payer denied the line for a missing authorization (CO-197).'],
  codes: ['CO-197'],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
};

const DRAFT = {
  label: 'draft for human review',
  text: LETTER,
  template_id: 'appeal-prior-authorization',
  rule_cards: ['ACME Health/appeal_levels', 'ACME Health/required_docs'],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
  drafted_at: '2026-10-31T12:05:00Z',
  edited_at: null,
};

/** A case body as `GET /cases/{id}` returns it. */
function caseBody({ diagnosis = DIAGNOSIS, draft = null, stale = false, draftStale = false } = {}) {
  return {
    ok: true,
    case_id: CASE,
    documents: [{ doc_id: 'src_0', kind: 'edi_835', filename: null }],
    extraction: {
      payer_name: read('ACME HEALTH PLAN'),
      claim_id: read('CLAIM-77'),
      billed_amount: read('250.00'),
      paid_amount: read('0.00'),
      adjustments: [],
      rarc_codes: [],
      lines: [],
      other_claims: 0,
      sources: ['src_0'],
    },
    needs_confirmation: [],
    diagnosis,
    diagnosis_stale: stale,
    draft,
    draft_stale: draftStale,
  };
}

/** A Hermes `ctx.rest` rejection carrying an envelope code. */
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

const exported = (format, changes = {}) => ({
  ok: true,
  case_id: CASE,
  format,
  path: PATH.replace('.pdf', `.${format}`),
  filename: `appeal-draft-${CASE}.${format}`,
  size_bytes: 1234,
  expires_at: EXPIRES,
  ...changes,
});

/** A worker that drafts on Draft appeal, stores edits, and exports, as plugin_api does. */
function backend() {
  const state = { body: caseBody(), calls: [], bodies: [] };
  const rest = async (path, opts) => {
    state.calls.push(path);
    state.bodies.push(opts?.body);
    if (path === `/cases/${CASE}/draft`) {
      state.body = caseBody({ draft: DRAFT });
      return { ok: true, case_id: CASE, job_id: DRAFT_JOB, kind: 'draft' };
    }
    if (path === `/cases/${CASE}/draft/text`) {
      state.body = caseBody({
        draft: { ...DRAFT, text: opts.body.text, edited_at: '2026-10-31T12:10:00Z' },
      });
      return state.body;
    }
    if (path === `/cases/${CASE}/export`) return exported(opts.body.format);
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
  return { ctx, element: casePaneOf(byArea(ctx.recorded).panes[0].render()) };
}

/** The pane's draft panel, rendered. */
const panelOf = (pane) => {
  const element = pane.props.children[at.draftPanel];
  return element.type(element.props);
};
const latest = (index = slot.current) => hooks.states[index].updates.at(-1);
const button = (panel, label) =>
  panel.props.children.find((c) => c?.type === 'button' && c.props.children === label);

afterEach(() => {
  runCleanups();
  setFileDownload(undefined);
});

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-7.1 draft is generated from rule card and template', () => {
  test('test_us_7_1_pane_draft_from_rule_card_and_template', async () => {
    const { rest, state } = backend();
    const { ctx, element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    assert.equal(ready.draft, undefined);
    const pane = rerender(element, ready, life());
    const draftButton = pane.props.children[at.draftButton];
    assert.equal(draftButton.props.children, 'Draft appeal');
    assert.equal(draftButton.props.disabled, false);
    assert.equal(
      pane.props.children[at.draftPanel].type(pane.props.children[at.draftPanel].props),
      null,
    );

    draftButton.props.onClick();
    await tick();
    assert.deepEqual(state.bodies.at(-1), {});
    assert.deepEqual(latest(), { state: 'processing', caseId: CASE, progress: 0, drafting: true });
    assert.equal(describeCase(latest()), `Drafting the appeal for case ${CASE} on this Mac… 0%`);
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: DRAFT_JOB, stage: 'drafting', progress: 0 });
    assert.deepEqual(latest(), { state: 'processing', caseId: CASE, progress: 0, drafting: true });
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: DRAFT_JOB, stage: 'done', progress: 1 });
    await tick();
    assert.equal(latest(slot.letter), null, 'the new draft replaces unsaved editor text');
    const drafted = latest();
    assert.equal(drafted.state, 'ready');
    assert.deepEqual(drafted.draft, {
      text: LETTER,
      templateId: 'appeal-prior-authorization',
      ruleCards: ['ACME Health/appeal_levels', 'ACME Health/required_docs'],
      stale: false,
      edited: false,
    });
    const panel = panelOf(rerender(element, drafted, life()));
    assert.equal(panel.props['aria-label'], 'Appeal draft');
    const [, provenance, staleNote, editor] = panel.props.children;
    assert.equal(
      provenance.props.children,
      'Drafted from the template appeal-prior-authorization with the rule cards ' +
        'ACME Health/appeal_levels, ACME Health/required_docs.',
    );
    assert.equal(staleNote, null);
    assert.equal(editor.props.value, LETTER, 'the draft letter is attached to the case');
    assert.deepEqual(hostAccesses, []);
  });

  test('the Draft appeal button needs a current diagnosis and says when it replaces edits', async () => {
    for (const [body, disabled] of [
      [caseBody({ diagnosis: null }), true],
      [caseBody({ stale: true }), true],
      [caseBody(), false],
    ]) {
      const ready = await openCase(
        createCaseApi(async () => body),
        CASE,
      );
      const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
      assert.equal(pane.props.children[at.draftButton].props.disabled, disabled);
    }
    const idle = rerender({ type: CasePane, props: { rest: async () => ({}) } });
    assert.equal(idle.props.children[at.draftButton].props.disabled, true);
    assert.equal(draftButtonLabel(undefined), 'Draft appeal');
    assert.equal(draftButtonLabel(draftOf(caseBody({ draft: DRAFT }))), 'Draft again');
    const edited = draftOf(caseBody({ draft: { ...DRAFT, edited_at: '2026-10-31T12:10:00Z' } }));
    assert.equal(draftButtonLabel(edited), 'Draft again (replaces your edits)');
  });

  test('Draft again waits for unsaved editor text; a refused start follows no job', async () => {
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const pane = { type: CasePane, props: { rest: async () => ({}) } };
    const dirty = rerender(pane, ready, life(), '', {}, 'Unsaved letter.', null);
    assert.equal(dirty.props.children[at.draftButton].props.disabled, true, 'save it first');
    const clean = rerender(pane, ready, life(), '', {}, DRAFT.text, null);
    assert.equal(clean.props.children[at.draftButton].props.disabled, false);

    const rest = async (path) => {
      if (path.endsWith('/draft')) throw rejection(409, 'not_diagnosed');
      return caseBody();
    };
    const { element } = mounted(rest);
    const shown = rerender(element, await openCase(createCaseApi(rest), CASE), life());
    shown.props.children[at.draftButton].props.onClick();
    assert.equal(hooks.states[slot.life].value.kind, 'draft', 'followed before the answer');
    await tick();
    await tick();
    assert.equal(latest().notice, 'not_diagnosed');
    const followed = hooks.states[slot.life].value;
    assert.deepEqual([followed.processing, followed.kind], [null, 'extract'], 'no job followed');
    assert.match(REFUSALS.draft_edited, /edits were kept/);
  });

  test('a failed or refused draft reopens the case with its fixed explanation', async () => {
    for (const [code, notice] of [
      ['model_unavailable', 'model_unavailable'],
      [null, 'drafting_failed'],
      ['internal_error', 'drafting_failed'],
    ]) {
      const { rest } = backend();
      const { ctx, element } = mounted(rest);
      const pane = rerender(element, await openCase(createCaseApi(rest), CASE), life());
      pane.props.children[at.draftButton].props.onClick();
      await tick();
      ctx.emit(PROGRESS_EVENT, {
        case_id: CASE,
        job_id: DRAFT_JOB,
        stage: 'failed',
        progress: 0,
        error_code: code,
      });
      await tick();
      assert.equal(latest().notice, notice);
      runCleanups();
    }
    for (const code of ['not_diagnosed', 'no_letter_template']) {
      const api = createCaseApi(async (path) => {
        if (path.endsWith('/draft')) throw rejection(409, code);
        return caseBody();
      });
      const refused = await draftCase(api, CASE);
      assert.equal(refused.notice, code);
      assert.ok(describeCase(refused).startsWith(REFUSALS[code]));
    }
  });

  test('a stale draft, a draft without rule cards, and malformed drafts', () => {
    const view = draftOf(caseBody({ draft: { ...DRAFT, rule_cards: [] }, draftStale: true }));
    const panel = DraftPanel({ draft: view, letter: null, result: null, disabled: false });
    const [, provenance, note] = panel.props.children;
    assert.match(provenance.props.children, /No rule card was on file for this payer/);
    assert.equal(
      note.props.children,
      'The case changed since this draft was made; check it, or draft again.',
    );
    assert.equal(panel.props['data-stale'], true);
    assert.equal(draftOf(null), null);
    assert.equal(draftOf({ draft: { ...DRAFT, text: '   ' } }), null);
    assert.equal(draftOf({ draft: { ...DRAFT, text: 7 } }), null);
    assert.equal(draftOf({ draft: { ...DRAFT, template_id: null } }), null);
    assert.deepEqual(draftOf({ draft: { ...DRAFT, rule_cards: 'x' } }).ruleCards, []);
  });
});

describe('US-7.1 draft carries the human-review label', () => {
  test('test_us_7_1_pane_draft_carries_review_label', () => {
    const panel = DraftPanel({
      draft: draftOf(caseBody({ draft: DRAFT })),
      letter: null,
      result: null,
      disabled: false,
    });
    const [heading, , , editor] = panel.props.children;
    assert.equal(heading.type, 'h3');
    assert.equal(heading.props.children, 'Draft for human review');
    assert.equal(editor.props['aria-label'], 'Appeal letter (draft for human review)');
    assert.equal(DRAFT_LABEL, 'draft for human review');
    for (const label of [undefined, 'final', 'Draft for human review']) {
      assert.equal(
        draftOf({ draft: { ...DRAFT, label } }),
        null,
        'an unlabeled draft is not shown',
      );
    }
  });
});

describe('US-7.2 edits are saved to the draft', () => {
  test('test_us_7_2_pane_edits_saved', async () => {
    const { rest, state } = backend();
    const { element } = mounted(rest);
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    let panel = panelOf(rerender(element, ready, life()));
    const editor = panel.props.children[3];
    assert.equal(button(panel, 'Save draft').props.disabled, true, 'nothing to save yet');

    const edited = LETTER.replace('To the appeals reviewer:', 'Dear reviewer,');
    editor.props.onChange({ currentTarget: { value: edited } });
    assert.equal(latest(slot.letter), edited);
    const pane = rerender(element, ready, life(), '', {}, edited, null);
    panel = panelOf(pane);
    assert.equal(panel.props.children[3].props.value, edited);
    assert.equal(button(panel, 'Export PDF').props.disabled, true, 'save before exporting');
    assert.equal(panel.props.children.at(-2).props.children, 'Save the draft before exporting it.');

    button(panel, 'Save draft').props.onClick();
    await tick();
    await tick();
    assert.equal(state.calls.at(-1), `/cases/${CASE}/draft/text`);
    assert.deepEqual(state.bodies.at(-1), { text: edited });
    const saved = latest();
    assert.equal(saved.draft.text, edited, 'the stored draft contains the edited text');
    assert.equal(saved.draft.edited, true);
    assert.equal(latest(slot.letter), null, 'the editor shows the stored text again');
  });

  test('a refused save keeps the text and explains; blank text is not sent', async () => {
    for (const [code, notice] of [
      ['invalid_request', 'invalid_draft'],
      ['case_closed', 'case_closed'],
      ['not_drafted', 'not_drafted'],
    ]) {
      const calls = [];
      const rest = async (path) => {
        calls.push(path);
        if (path.endsWith('/draft/text')) throw rejection(409, code);
        return caseBody({ draft: DRAFT });
      };
      const { element } = mounted(rest);
      const ready = await openCase(createCaseApi(rest), CASE);
      const panel = panelOf(rerender(element, ready, life(), '', {}, 'Edited.', null));
      button(panel, 'Save draft').props.onClick();
      await tick();
      await tick();
      assert.equal(latest().notice, notice);
      assert.equal(hooks.states[slot.letter].updates.length, 0, 'the text stays in the editor');
      runCleanups();
    }
    const unknown = await saveDraft(
      createCaseApi(async () => {
        throw new Error('boom');
      }),
      CASE,
      'x',
    );
    assert.deepEqual(unknown, { state: 'unavailable' });
    const wrong = await saveDraft(
      createCaseApi(async () => ({ case_id: 'other' })),
      CASE,
      'x',
    );
    assert.deepEqual(wrong, { state: 'unavailable' });

    const calls = [];
    const { element } = mounted(async (path) => {
      calls.push(path);
      return caseBody({ draft: DRAFT });
    });
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const blank = rerender(element, ready, life(), '', {}, '   ', null);
    const save = button(panelOf(blank), 'Save draft');
    assert.equal(save.props.disabled, true);
    save.props.onClick();
    const notReady = rerender(element, { state: 'busy' }, life(), '', {}, 'Edited.', null);
    notReady.props.children[at.draftButton].props.onClick();
    assert.ok(!calls.some((path) => path.includes('/draft')), 'nothing is sent');
  });
});

describe('US-7.2 export produces PDF and DOCX through the save dialog', () => {
  test('test_us_7_2_pane_export_pdf', async () => {
    const saves = [];
    const order = [];
    setFileDownload(() => {
      order.push('captured');
      return async (path, name) => {
        saves.push([path, name]);
      };
    });
    const { rest, state } = backend();
    const tracked = async (path, opts) => {
      if (path.endsWith('/export')) order.push('requested');
      return rest(path, opts);
    };
    const { element } = mounted(tracked);
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const panel = panelOf(rerender(element, ready, life()));
    button(panel, 'Export PDF').props.onClick();
    await tick();
    await tick();
    assert.deepEqual(state.bodies.at(-1), { format: 'pdf' });
    assert.deepEqual(order, ['captured', 'requested'], 'captured before the REST read');
    assert.deepEqual(saves, [[PATH, `appeal-draft-${CASE}.pdf`]], 'the save dialog gets the file');
    const result = latest(slot.exported);
    assert.deepEqual(result, { state: 'saved', format: 'pdf' });
    const shown = panelOf(rerender(element, ready, life(), '', {}, null, result));
    assert.equal(shown.props.children.at(-1).props.children, 'The PDF went to the save dialog.');
  });

  test('test_us_7_2_pane_export_docx', async () => {
    const saves = [];
    setFileDownload(() => async (path, name) => {
      saves.push([path, name]);
    });
    const { rest, state } = backend();
    const { element } = mounted(rest);
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    button(panelOf(rerender(element, ready, life())), 'Export DOCX').props.onClick();
    await tick();
    await tick();
    assert.deepEqual(state.bodies.at(-1), { format: 'docx' });
    assert.deepEqual(saves, [[PATH.replace('.pdf', '.docx'), `appeal-draft-${CASE}.docx`]]);
    assert.deepEqual(latest(slot.exported), { state: 'saved', format: 'docx' });
  });

  test('test_us_7_2_pane_without_save_dialog_shows_where_the_file_is', async () => {
    const api = createCaseApi(async () => exported('pdf'));
    const result = await exportDraft(api, CASE, 'pdf', undefined);
    assert.deepEqual(result, { state: 'written', format: 'pdf', path: PATH, expiresAt: EXPIRES });
    assert.equal(
      describeExport(result),
      `The PDF is on this Mac at ${PATH} until ${EXPIRES}; copy it from there before it is removed.`,
    );
  });

  test('refused, failed, and malformed exports; a late answer for another case is dropped', async () => {
    const refusing = createCaseApi(async () => {
      throw rejection(409, 'not_drafted');
    });
    const refused = await exportDraft(refusing, CASE, 'pdf', undefined);
    assert.deepEqual(refused, { state: 'refused', notice: 'not_drafted' });
    assert.equal(describeExport(refused), REFUSALS.not_drafted);
    const failing = createCaseApi(async () => {
      throw new Error('500: oops');
    });
    assert.deepEqual(await exportDraft(failing, CASE, 'pdf', undefined), { state: 'failed' });
    assert.match(describeExport({ state: 'failed' }), /did not finish/);
    for (const changes of [
      { case_id: 'case_other' },
      { path: '' },
      { path: 7 },
      { filename: 'appeal.exe' },
      { filename: null },
      { expires_at: null },
    ]) {
      const api = createCaseApi(async () => exported('pdf', changes));
      assert.deepEqual(await exportDraft(api, CASE, 'pdf', undefined), { state: 'failed' });
    }
    assert.deepEqual(
      await exportDraft(
        createCaseApi(async () => null),
        CASE,
        'pdf',
        undefined,
      ),
      {
        state: 'failed',
      },
    );

    let answer;
    const slow = new Promise((resolve) => {
      answer = resolve;
    });
    const { element } = mounted(async (path) => (path.endsWith('/export') ? slow : caseBody()));
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const elsewhere = { ...life(), caseId: 'case_ffffffffffffffff' };
    button(panelOf(rerender(element, ready, elsewhere)), 'Export PDF').props.onClick();
    answer(exported('pdf'));
    await tick();
    assert.deepEqual(
      hooks.states[slot.exported].updates.at(-1),
      { state: 'exporting', format: 'pdf' },
      'the answer for another case is not shown',
    );
    const idle = rerender(element, { state: 'idle' }, life());
    assert.equal(panelOf(idle), null);
    const noDraft = DraftPanel({ draft: undefined, letter: null, result: null, disabled: true });
    assert.equal(noDraft, null);
  });

  test('Export does nothing without a ready case holding a draft', async () => {
    const calls = [];
    const { element } = mounted(async (path) => {
      calls.push(path);
      return caseBody();
    });
    const busy = rerender(element, { state: 'busy' }, life());
    busy.props.children[at.draftPanel].props.onExport('pdf');
    const withoutDraft = await openCase(
      createCaseApi(async () => caseBody()),
      CASE,
    );
    const rendered = rerender(element, withoutDraft, life());
    const props = rendered.props.children[at.draftPanel].props;
    props.onExport('pdf');
    props.onSave();
    assert.deepEqual(
      calls.filter((path) => path.includes('/export') || path.includes('/draft')),
      [],
    );
  });

  test('one export at a time: the buttons wait for the answer', async () => {
    const calls = [];
    const { element } = mounted(async (path) => {
      calls.push(path);
      return caseBody({ draft: DRAFT });
    });
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const exporting = { state: 'exporting', format: 'pdf' };
    const panel = panelOf(rerender(element, ready, life(), '', {}, null, exporting));
    assert.equal(button(panel, 'Export PDF').props.disabled, true);
    assert.equal(button(panel, 'Export DOCX').props.disabled, true);
    assert.equal(panel.props.children.at(-1).props.children, 'Exporting the PDF…');
    button(panel, 'Export DOCX').props.onClick();
    assert.deepEqual(
      calls.filter((path) => path.endsWith('/export')),
      [],
      'a second export waits',
    );
  });

  test('New case clears the editor and the export result', async () => {
    const { element } = mounted(async () => caseBody({ draft: DRAFT }));
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft: DRAFT })),
      CASE,
    );
    const pane = rerender(element, ready, life(), '', {}, 'Unsaved.', { state: 'failed' });
    pane.props.children[5].props.onClick(); // New case
    assert.equal(latest(slot.letter), null);
    assert.equal(latest(slot.exported), null);
  });
});

describe('US-7.3 no contribution offers send or submit', () => {
  test('test_us_7_3_no_send_contribution', async () => {
    const { rest } = backend();
    const ctx = createFakeCtx({ rest, events: true });
    plugin.register(ctx);
    const contributions = ctx.recorded.contributions;
    assert.ok(contributions.length >= 4, 'every contribution was collected');
    assert.equal(ctx.recorded.settingsPages.length, 1, 'the settings page was collected');
    const strings = [];
    const links = [];
    let controls = 0;
    for (const contribution of [...contributions, ...ctx.recorded.settingsPages]) {
      strings.push(contribution.id, contribution.title ?? '');
      for (const value of Object.values(contribution.data ?? {})) {
        if (typeof value === 'string') strings.push(value);
      }
      if (contribution.render) {
        const found = controlStrings(contribution.render());
        strings.push(...found.strings);
        links.push(...found.links);
        controls += found.controls;
        runCleanups(); // the statusbar item's refresh timer
      }
    }
    // The case pane in every state, a diagnosed case with a stale, edited draft and an export.
    const pane = casePaneOf(byArea(ctx.recorded).panes[0].render());
    const draft = { ...DRAFT, edited_at: '2026-10-31T12:10:00Z' };
    const ready = await openCase(
      createCaseApi(async () => caseBody({ draft, draftStale: true })),
      CASE,
    );
    for (const seed of [
      [{ state: 'idle' }],
      [{ state: 'busy' }],
      [{ state: 'processing', caseId: CASE, progress: 0.5, drafting: true }],
      [{ state: 'unavailable' }],
      [ready, life(), 'pasted', {}, 'Unsaved letter.', { state: 'saved', format: 'pdf' }],
      [
        ready,
        life(),
        '',
        {},
        null,
        { state: 'written', format: 'docx', path: PATH, expiresAt: EXPIRES },
      ],
    ]) {
      const found = controlStrings(rerender(pane, ...seed));
      strings.push(...found.strings);
      links.push(...found.links);
      controls += found.controls;
      runCleanups();
    }
    assert.ok(controls >= 40, `the walk saw the pane's controls (${controls})`);
    assert.ok(
      strings.includes('Export PDF') && strings.includes('Draft again (replaces your edits)'),
    );
    const offending = strings.filter((text) => SEND.test(text));
    assert.deepEqual(offending, [], 'no label or command sends or submits to a payer');
    assert.ok(!strings.includes('<form>'), 'no form posts anywhere');
    assert.deepEqual(
      links.filter((link) => ABSOLUTE.test(link)),
      [],
      'no link leaves the app',
    );
  });

  test('the check catches a send control', () => {
    const memo = { $$typeof: Symbol.for('react.memo'), type: 'button' };
    const forward = { render: (props) => ({ type: 'button', props }) };
    const Fancy = ({ text }) => ({ type: 'button', props: { onClick() {}, children: text } });
    const found = controlStrings({
      type: 'section',
      props: {
        children: [
          { type: 'button', props: { children: 'Submit to payer', onClick() {} } },
          { type: 'a', props: { href: 'mailto:appeals@payer.example', children: 'Appeals' } },
          { type: 'a', props: { href: 'https://portal.payer.example/appeals', children: 'Open' } },
          { type: 'form', props: { action: 'https://payer.example/upload', children: [] } },
          { type: 'span', props: { children: 'Fax it', onClick() {} } },
          {
            type: 'button',
            props: { onClick() {}, children: { type: 'span', props: { children: 'Send now' } } },
          },
          { type: 'button', props: { children: [{ type: 'svg', props: {} }, 'E-mail it'] } },
          {
            type: 'label',
            props: {
              children: [{ type: 'input', props: { type: 'checkbox' } }, 'Auto-submit when saved'],
            },
          },
          { type: memo, props: { children: 'Resend to payer' } },
          { type: forward, props: { children: 'File with the clearinghouse' } },
          { type: Fancy, props: { text: 'Transmit' } },
          { type: 'input', props: { placeholder: 'Payer portal login' } },
          { type: 'button', props: { 'aria-description': 'delivers the letter', children: 'Go' } },
          { type: 'p', props: { children: 'Text outside a control is not a control.' } },
        ],
      },
    });
    assert.deepEqual(
      found.strings.filter((text) => SEND.test(text)),
      [
        'Submit to payer',
        'Fax it',
        'Send now',
        'E-mail it',
        'Auto-submit when saved',
        'Resend to payer',
        'File with the clearinghouse',
        'Transmit',
        'Payer portal login',
        'delivers the letter',
      ],
    );
    assert.ok(found.strings.includes('<form>'));
    assert.deepEqual(
      found.links.filter((link) => ABSOLUTE.test(link)),
      [
        'mailto:appeals@payer.example',
        'https://portal.payer.example/appeals',
        'https://payer.example/upload',
      ],
    );
    assert.ok(!found.strings.includes('Text outside a control is not a control.'));
    assert.ok(!SEND.test('Export PDF') && !SEND.test('Consent') && !SEND.test('Represented'));
  });
});
