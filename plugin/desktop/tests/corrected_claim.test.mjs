/**
 * node --test suite for the corrected claim in the pane. US-7.4 scenarios:
 *   - An appeal-only denial gets a recommendation, not a corrected-claim draft
 *   - A correctable denial gets a list of changes for human review
 *   - A value missing from the documents is never invented
 *   - A draft goes stale after re-extraction
 *   - The label is always present
 *   - The corrected-claim draft exports as PDF or DOCX
 *   - No submit control
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  CasePane,
  CORRECTABLE_FIELDS,
  CorrectionPanel,
  correctCase,
  correctionButtonLabel,
  correctionOf,
  createCaseApi,
  describeCase,
  describeChange,
  exportCorrection,
  FREQUENCY_CODES,
  NOT_IN_DOCUMENTS,
  openCase,
  PROGRESS_EVENT,
  REFUSALS,
  REMEDIES,
  RemedyLine,
  remedyOf,
} from '../plugin.js';
import { ABSOLUTE, controlStrings, SEND } from './controls.mjs';
import { byArea, casePaneOf, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses, setFileDownload } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const JOB = 'job_0ccccccccccccccc';
const at = { remedy: 14, draftButton: 15, button: 17, panel: 18 };
const slot = { current: 0, life: 1, corrected: 7 };
const EXPIRES = '2026-10-31T12:15:00Z';
const PATH = `/Users/biller/.hermes/plugin-data/claimcoach/exports/corrected-claim-draft-${CASE}-0f.pdf`;
const ACTION = "Check the modifier against the visit's documentation.";
const WHY = 'CO-4 says the procedure code does not fit its modifier.';

const read = (value) => ({ value, status: 'extracted' });

const DIAGNOSIS = {
  denial_reason: 'coding_error',
  appeal_likelihood: 'medium',
  likelihood_reasons: ['The procedure code and its modifier disagree (CO-4).'],
  codes: ['CO-4', 'M51'],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
};

const REMEDY = {
  remedy: 'corrected_claim',
  basis: 'table',
  denial_reason: 'coding_error',
  codes: [],
  rule_card: null,
};

const CORRECTION = {
  label: 'draft for human review',
  original_claim_id: 'CLAIM-77',
  frequency_code: '7',
  corrections: [
    {
      line: 1,
      field: 'modifier',
      current_value: null,
      because: ['CO-4'],
      action: ACTION,
      why: WHY,
    },
    {
      line: 1,
      field: 'procedure_code',
      current_value: '99213',
      because: ['CO-4', 'M51'],
      action: 'Check the procedure code against the visit note.',
      why: 'M51 says the procedure code is missing or invalid.',
    },
  ],
  rule_cards: ['ACME Health/corrected_claims'],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
  drafted_at: '2026-10-31T12:05:00Z',
};

/** A case body as `GET /cases/{id}` returns it. */
function caseBody({
  diagnosis = DIAGNOSIS,
  remedy = REMEDY,
  correction = null,
  stale = false,
  correctionStale = false,
} = {}) {
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
    remedy,
    draft: null,
    draft_stale: false,
    correction,
    correction_stale: correctionStale,
  };
}

const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

const exported = (format, changes = {}) => ({
  ok: true,
  case_id: CASE,
  format,
  path: PATH.replace('.pdf', `.${format}`),
  filename: `corrected-claim-draft-${CASE}.${format}`,
  size_bytes: 1234,
  expires_at: EXPIRES,
  ...changes,
});

/** A worker that drafts the corrected claim and exports it, as plugin_api does. */
function backend() {
  const state = { body: caseBody(), calls: [], bodies: [] };
  const rest = async (path, opts) => {
    state.calls.push(path);
    state.bodies.push(opts?.body);
    if (path === `/cases/${CASE}/correction`) {
      state.body = caseBody({ correction: CORRECTION });
      return { ok: true, case_id: CASE, job_id: JOB, kind: 'correct' };
    }
    if (path === `/cases/${CASE}/correction/export`) return exported(opts.body.format);
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

/** Seed the pane's state: the case, its life, and (at slot 7) the corrected-claim export. */
function seeded(element, ready, corrected = null) {
  return rerender(element, ready, life(), '', {}, null, null, null, corrected);
}

function mounted(rest) {
  const ctx = createFakeCtx({ rest, events: true });
  plugin.register(ctx);
  return { ctx, element: casePaneOf(byArea(ctx.recorded).panes[0].render()) };
}

const render = (element) => element.type(element.props);
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

describe('US-7.4 an appeal-only denial gets a recommendation, not a corrected-claim draft', () => {
  test('test_us_7_4_pane_appeal_only_denial_gets_a_recommendation', async () => {
    const appeal = { ...REMEDY, remedy: 'appeal', denial_reason: 'medical_necessity' };
    const ready = await openCase(
      createCaseApi(async () => caseBody({ remedy: appeal })),
      CASE,
    );
    assert.deepEqual(ready.remedy, { remedy: 'appeal', basis: 'table', codes: [], card: null });
    assert.equal(ready.correction, undefined, 'nothing drafted unasked');
    const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
    const line = pane.props.children[at.remedy];
    assert.equal(line.props['aria-label'], 'Recommended fix');
    const [recommendation, why] = line.props.children;
    assert.equal(recommendation.props.children, 'Recommended fix: an appeal.');
    assert.equal(
      why.props.children,
      "From ClaimCoach's table for this denial reason. You can draft either one.",
    );
    assert.equal(render(pane.props.children[at.panel]), null, 'no corrected-claim draft shown');
    const draftCorrected = pane.props.children[at.button];
    assert.equal(draftCorrected.props.children, 'Draft corrected claim');
    assert.equal(draftCorrected.props.disabled, false, 'the biller can still ask for one');
    assert.equal(pane.props.children[at.draftButton].props.disabled, false);
  });

  test('the recommendation says what decided it; malformed ones are not shown', () => {
    const codes = RemedyLine(remedyOf({ remedy: { ...REMEDY, basis: 'codes', codes: ['CO-31'] } }));
    assert.equal(
      codes.props.children[1].props.children,
      'From the codes CO-31. You can draft either one.',
    );
    const card = RemedyLine(
      remedyOf({
        remedy: { ...REMEDY, basis: 'rule_card', rule_card: 'ACME Health/corrected_claims' },
      }),
    );
    assert.match(card.props.children[1].props.children, /rule card ACME Health\/corrected_claims/);
    for (const remedy of Object.keys(REMEDIES)) {
      const shown = RemedyLine(remedyOf({ remedy: { ...REMEDY, remedy } }));
      assert.equal(shown.props.children[0].props.children, REMEDIES[remedy]);
    }
    assert.equal(RemedyLine(undefined), null);
    for (const remedy of [
      null,
      { ...REMEDY, remedy: 'submit' },
      { ...REMEDY, remedy: 7 },
      { ...REMEDY, basis: 'model' },
      { ...REMEDY, basis: null },
    ]) {
      assert.equal(remedyOf({ remedy }), null);
    }
    assert.equal(remedyOf(null), null);
    assert.deepEqual(remedyOf({ remedy: { ...REMEDY, codes: 'x' } }).codes, []);
  });
});

describe('US-7.4 a correctable denial gets a list of changes for human review', () => {
  test('test_us_7_4_pane_correctable_denial_gets_a_list_of_changes', async () => {
    const { rest, state } = backend();
    const { ctx, element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    const pane = rerender(element, ready, life());
    assert.equal(
      pane.props.children[at.remedy].props.children[0].props.children,
      REMEDIES.corrected_claim,
    );

    pane.props.children[at.button].props.onClick();
    assert.equal(hooks.states[slot.life].value.kind, 'correct', 'followed before the answer');
    await tick();
    assert.deepEqual(state.bodies.at(-1), {});
    assert.deepEqual(latest(), {
      state: 'processing',
      caseId: CASE,
      progress: 0,
      correcting: true,
    });
    assert.equal(
      describeCase(latest()),
      `Drafting the corrected claim for case ${CASE} on this Mac… 0%`,
    );
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'drafting', progress: 0 });
    assert.deepEqual(latest(), {
      state: 'processing',
      caseId: CASE,
      progress: 0,
      correcting: true,
    });
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: JOB, stage: 'done', progress: 1 });
    await tick();
    const drafted = latest();
    assert.equal(drafted.state, 'ready');
    assert.equal(drafted.correction.changes.length, 2);
    const shown = rerender(element, drafted, life());
    assert.equal(shown.props.children[at.button].props.children, 'Draft corrected claim again');
    const panel = render(shown.props.children[at.panel]);
    assert.equal(panel.props['aria-label'], 'Corrected-claim draft');
    const [heading, summary, staleNote, list] = panel.props.children;
    assert.equal(heading.props.children, 'Corrected claim: draft for human review');
    assert.equal(
      summary.props.children,
      'Original claim number: CLAIM-77. Claim frequency code 7 (a replacement of the prior ' +
        'claim). Drafted with the rule cards ACME Health/corrected_claims. Make and check these ' +
        'changes in your billing system; ClaimCoach does not file claims.',
    );
    assert.equal(staleNote, null);
    assert.equal(list.props['aria-label'], 'Changes');
    assert.deepEqual(
      list.props.children.map((item) => item.props.children),
      [
        `Line 1, modifier (current value: ${NOT_IN_DOCUMENTS}): ${ACTION} Why: ${WHY} Codes: CO-4.`,
        'Line 1, procedure code (current value: 99213): Check the procedure code against the ' +
          'visit note. Why: M51 says the procedure code is missing or invalid. Codes: CO-4, M51.',
      ],
      'each change names a line, a field, an action, and the codes behind it',
    );
    assert.deepEqual(hostAccesses, []);
  });

  test('the Draft corrected claim button needs a current, open, diagnosed case', async () => {
    for (const [body, disabled] of [
      [caseBody({ diagnosis: null, remedy: null }), true],
      [caseBody({ stale: true, remedy: null }), true],
      [{ ...caseBody(), closed_at: '2026-10-31T13:00:00Z' }, true],
      [caseBody(), false],
    ]) {
      const ready = await openCase(
        createCaseApi(async () => body),
        CASE,
      );
      const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
      assert.equal(pane.props.children[at.button].props.disabled, disabled);
    }
    const idle = rerender({ type: CasePane, props: { rest: async () => ({}) } });
    assert.equal(idle.props.children[at.button].props.disabled, true);
    const calls = [];
    const { element } = mounted(async (path) => {
      calls.push(path);
      return caseBody();
    });
    rerender(element, { state: 'busy' }, life()).props.children[at.button].props.onClick();
    assert.ok(!calls.some((path) => path.endsWith('/correction')), 'nothing is started');
    assert.equal(correctionButtonLabel(undefined), 'Draft corrected claim');
  });

  test('a failed or refused corrected-claim draft reopens the case with its fixed explanation', async () => {
    for (const [code, notice] of [
      ['correction_failed', 'correction_failed'],
      [null, 'correction_failed'],
      ['model_unavailable', 'model_unavailable'],
    ]) {
      const { rest } = backend();
      const { ctx, element } = mounted(rest);
      const pane = rerender(element, await openCase(createCaseApi(rest), CASE), life());
      pane.props.children[at.button].props.onClick();
      await tick();
      ctx.emit(PROGRESS_EVENT, {
        case_id: CASE,
        job_id: JOB,
        stage: 'failed',
        progress: 0,
        error_code: code,
      });
      await tick();
      assert.equal(latest().notice, notice);
      runCleanups();
    }
    const api = createCaseApi(async (path) => {
      if (path.endsWith('/correction')) throw rejection(409, 'not_diagnosed');
      return caseBody();
    });
    const refused = await correctCase(api, CASE);
    assert.equal(refused.notice, 'not_diagnosed');
    assert.match(REFUSALS.correction_failed, /draft it again, or draft an appeal/);
    const running = await correctCase(
      createCaseApi(async () => ({ ok: true, case_id: CASE, job_id: JOB, kind: 'draft' })),
      CASE,
    );
    assert.equal(running.drafting, true, 'the case was already drafting its appeal');
  });
});

describe('US-7.4 a value missing from the documents is never invented', () => {
  test('test_us_7_4_pane_value_missing_from_documents_is_never_invented', () => {
    const view = correctionOf(caseBody({ correction: CORRECTION }));
    assert.equal(view.changes[0].current, null);
    assert.match(describeChange(view.changes[0]), /current value: not in your documents/);
    const claimLevel = describeChange({
      line: null,
      field: 'member_id',
      current: null,
      because: [],
      action: 'Check the member ID on the insurance card.',
      why: 'CO-31: the payer could not match the patient.',
    });
    assert.equal(
      claimLevel,
      'Claim, member ID (current value: not in your documents): Check the member ID on the ' +
        'insurance card. Why: CO-31: the payer could not match the patient. Codes: none read.',
      'a change with no codes read says so',
    );
    const bare = CorrectionPanel({
      correction: correctionOf(
        caseBody({ correction: { ...CORRECTION, original_claim_id: null, rule_cards: [] } }),
      ),
      result: null,
      disabled: false,
      onExport() {},
    });
    assert.match(
      bare.props.children[1].props.children,
      /^Original claim number: not in your documents\./,
    );
    assert.doesNotMatch(bare.props.children[1].props.children, /rule cards/);
    assert.equal(Object.keys(CORRECTABLE_FIELDS).length, 11);
  });
});

describe('US-7.4 a draft goes stale after re-extraction', () => {
  test('test_us_7_4_pane_draft_goes_stale_after_re_extraction', () => {
    const view = correctionOf(caseBody({ correction: CORRECTION, correctionStale: true }));
    assert.equal(view.stale, true);
    const panel = CorrectionPanel({
      correction: view,
      result: null,
      disabled: false,
      onExport() {},
    });
    assert.equal(panel.props['data-stale'], true);
    assert.equal(
      panel.props.children[2].props.children,
      'The case changed since this draft was made; check it, or draft it again.',
    );
    assert.equal(
      correctionButtonLabel(view),
      'Draft corrected claim again',
      'it offers to redraft',
    );
  });

  test('changed fields: re-diagnose first, then Draft corrected claim again is offered', async () => {
    // Review: changed fields make the diagnosis stale too, so the button waits for a diagnosis.
    const pane = { type: CasePane, props: { rest: async () => ({}) } };
    const changed = await openCase(
      createCaseApi(async () =>
        caseBody({ correction: CORRECTION, correctionStale: true, stale: true, remedy: null }),
      ),
      CASE,
    );
    const waiting = rerender(pane, changed, life());
    assert.equal(waiting.props.children[at.button].props.disabled, true);
    assert.match(describeCase(changed), /diagnose the case again/);
    assert.equal(render(waiting.props.children[at.panel]).props['data-stale'], true);
    const rediagnosed = await openCase(
      createCaseApi(async () => caseBody({ correction: CORRECTION, correctionStale: true })),
      CASE,
    );
    const offered = rerender(pane, rediagnosed, life()).props.children[at.button];
    assert.equal(offered.props.disabled, false);
    assert.equal(offered.props.children, 'Draft corrected claim again');
  });

  test('changes the draft does not list are counted, so every line is checked', () => {
    const view = correctionOf(caseBody({ correction: { ...CORRECTION, omitted: 20 } }));
    assert.equal(view.omitted, 20);
    const panel = CorrectionPanel({
      correction: view,
      result: null,
      disabled: false,
      onExport() {},
    });
    const note = panel.props.children[4];
    assert.equal(note.props.role, 'note');
    assert.match(note.props.children, /^20 more change\(s\) are not listed/);
    const none = correctionOf(caseBody({ correction: { ...CORRECTION, omitted: -1 } }));
    assert.equal(none.omitted, 0);
    const listed = CorrectionPanel({
      correction: none,
      result: null,
      disabled: false,
      onExport() {},
    });
    assert.equal(listed.props.children[4], null);
  });
});

describe('US-7.4 the label is always present', () => {
  test('test_us_7_4_pane_label_is_always_present', () => {
    for (const label of [undefined, 'final claim', 'Draft for human review']) {
      assert.equal(correctionOf(caseBody({ correction: { ...CORRECTION, label } })), null);
    }
    for (const changes of [
      { frequency_code: '2' },
      { frequency_code: 7 },
      { corrections: [] },
      { corrections: 'none' },
      { corrections: [{ ...CORRECTION.corrections[0], field: 'npi' }] },
      { corrections: [{ ...CORRECTION.corrections[0], line: 0 }] },
      { corrections: [{ ...CORRECTION.corrections[0], line: 'one' }] },
      { corrections: [{ ...CORRECTION.corrections[0], action: null }] },
      { corrections: [{ ...CORRECTION.corrections[0], why: 7 }] },
      { corrections: [null] },
    ]) {
      assert.equal(correctionOf(caseBody({ correction: { ...CORRECTION, ...changes } })), null);
    }
    assert.equal(correctionOf(null), null);
    const loose = correctionOf(
      caseBody({
        correction: {
          ...CORRECTION,
          rule_cards: 'x',
          corrections: [{ ...CORRECTION.corrections[1], current_value: 7, because: 'CO-4' }],
        },
      }),
    );
    assert.deepEqual(loose.ruleCards, []);
    assert.deepEqual([loose.changes[0].current, loose.changes[0].because], [null, []]);
    assert.equal(
      CorrectionPanel({ correction: undefined, result: null, disabled: false, onExport() {} }),
      null,
    );
    assert.deepEqual(Object.keys(FREQUENCY_CODES), ['1', '7', '8']);
  });
});

describe('US-7.4 the corrected-claim draft exports as PDF or DOCX', () => {
  test('test_us_7_4_pane_export_pdf_and_docx', async () => {
    const saves = [];
    setFileDownload(() => async (path, name) => {
      saves.push([path, name]);
    });
    const { rest, state } = backend();
    const { element } = mounted(rest);
    const ready = await openCase(
      createCaseApi(async () => caseBody({ correction: CORRECTION })),
      CASE,
    );
    const panel = render(seeded(element, ready).props.children[at.panel]);
    button(panel, 'Export corrected claim PDF').props.onClick();
    await tick();
    await tick();
    assert.equal(state.calls.at(-1), `/cases/${CASE}/correction/export`);
    assert.deepEqual(state.bodies.at(-1), { format: 'pdf' });
    assert.deepEqual(saves, [[PATH, `corrected-claim-draft-${CASE}.pdf`]]);
    assert.deepEqual(latest(slot.corrected), { state: 'saved', format: 'pdf' });

    const again = render(seeded(element, ready).props.children[at.panel]);
    button(again, 'Export corrected claim DOCX').props.onClick();
    await tick();
    await tick();
    assert.deepEqual(state.bodies.at(-1), { format: 'docx' });
    assert.deepEqual(latest(slot.corrected), { state: 'saved', format: 'docx' });
    const shown = render(
      seeded(element, ready, { state: 'saved', format: 'docx' }).props.children[at.panel],
    );
    const status = shown.props.children.at(-1);
    assert.equal(status.props['aria-label'], 'Corrected-claim export');
    assert.equal(status.props.children, 'The DOCX went to the save dialog.');
  });

  test('refused, failed, and unsaved exports; one at a time; a late answer is dropped', async () => {
    const api = (answer) =>
      createCaseApi(async () => {
        if (answer instanceof Error) throw answer;
        return answer;
      });
    assert.deepEqual(await exportCorrection(api(rejection(409, 'not_corrected')), CASE, 'pdf'), {
      state: 'refused',
      notice: 'not_corrected',
    });
    assert.deepEqual(await exportCorrection(api(new Error('boom')), CASE, 'pdf'), {
      state: 'failed',
    });
    assert.deepEqual(
      await exportCorrection(api(exported('pdf', { filename: 'x.docx' })), CASE, 'pdf'),
      {
        state: 'failed',
      },
    );
    assert.deepEqual(await exportCorrection(api(exported('pdf')), CASE, 'pdf'), {
      state: 'written',
      format: 'pdf',
      path: PATH,
      expiresAt: EXPIRES,
    });

    const ready = await openCase(
      createCaseApi(async () => caseBody({ correction: CORRECTION })),
      CASE,
    );
    const exporting = render(
      seeded(element(), ready, { state: 'exporting', format: 'pdf' }).props.children[at.panel],
    );
    assert.ok(
      exporting.props.children.filter((c) => c?.type === 'button').every((b) => b.props.disabled),
    );

    const calls = [];
    const { element: busy } = mounted(async (path) => {
      calls.push(path);
      return caseBody({ correction: CORRECTION });
    });
    const busyPane = seeded(busy, ready, { state: 'exporting', format: 'pdf' });
    button(render(busyPane.props.children[at.panel]), 'Export corrected claim PDF').props.onClick();
    const noDraft = await openCase(
      createCaseApi(async () => caseBody()),
      CASE,
    );
    const plain = seeded(busy, noDraft);
    plain.props.children[at.panel].props.onExport('pdf');
    seeded(busy, { state: 'busy' }).props.children[at.panel].props.onExport('pdf');
    assert.ok(!calls.some((path) => path.endsWith('/export')), 'nothing is exported');

    let answer;
    const { element: slow } = mounted(async (path) => {
      if (path.endsWith('/export')) {
        return new Promise((resolve) => {
          answer = resolve;
        });
      }
      return caseBody({ correction: CORRECTION });
    });
    const slowPane = seeded(slow, ready);
    button(render(slowPane.props.children[at.panel]), 'Export corrected claim PDF').props.onClick();
    hooks.states[slot.life].value.caseId = 'case_ffffffffffffffff'; // another case opened
    answer(exported('pdf'));
    await tick();
    await tick();
    assert.deepEqual(
      hooks.states[slot.corrected].updates,
      [{ state: 'exporting', format: 'pdf' }],
      'the late answer is not shown for another case',
    );
  });

  test('New case and a new action clear the corrected-claim export', async () => {
    const { rest } = backend();
    const { element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    const pane = seeded(element, ready, { state: 'saved', format: 'pdf' });
    pane.props.children[5].props.onClick(); // New case
    assert.deepEqual(latest(slot.corrected), null);
    const again = seeded(element, ready, { state: 'saved', format: 'pdf' });
    again.props.children[at.button].props.onClick(); // a new action starts: the export is old
    assert.deepEqual(latest(slot.corrected), null);
  });
});

describe('US-7.4 no submit control', () => {
  test('test_us_7_4_pane_no_submit_control', async () => {
    const ready = await openCase(
      createCaseApi(async () => caseBody({ correction: CORRECTION, correctionStale: true })),
      CASE,
    );
    const strings = [];
    const links = [];
    for (const corrected of [
      null,
      { state: 'exporting', format: 'pdf' },
      { state: 'written', format: 'docx', path: PATH, expiresAt: EXPIRES },
    ]) {
      const found = controlStrings(seeded(element(), ready, corrected));
      strings.push(...found.strings);
      links.push(...found.links);
    }
    const processing = { state: 'processing', caseId: CASE, progress: 0.5, correcting: true };
    strings.push(...controlStrings(rerender(element(), processing, life())).strings);
    assert.ok(strings.includes('Draft corrected claim again'));
    assert.ok(strings.includes('Export corrected claim PDF'));
    assert.deepEqual(
      strings.filter((text) => SEND.test(text)),
      [],
      'no corrected-claim control sends, submits, or files anything',
    );
    assert.deepEqual(
      links.filter((link) => ABSOLUTE.test(link)),
      [],
    );
  });
});

/** A case pane element that is not registered with a host (no events). */
function element() {
  return { type: CasePane, props: { rest: async () => ({}) } };
}
