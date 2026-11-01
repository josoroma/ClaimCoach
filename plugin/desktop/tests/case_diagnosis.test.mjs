/**
 * node --test suite for the diagnosis in the pane. US-6.1 scenarios:
 *   - Appeal likelihood includes reasons
 *   - The pane diagnoses after extraction
 *   - A confirmed field makes the diagnosis stale
 * US-6.2 scenarios:
 *   - Explanation and root cause are shown
 *   - Checklist lists missing documentation
 *   - No rule card for the payer
 * US-6.3 scenarios:
 *   - Deadline is computed from the rule card
 *   - The deadline has passed
 *   - An unknown deadline says why
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  afterExtraction,
  CasePane,
  ChecklistPanel,
  createCaseApi,
  DEADLINE_UNKNOWN,
  DENIAL_REASONS,
  DeadlineLine,
  DiagnosisPanel,
  describeCase,
  describeDeadline,
  diagnoseCase,
  diagnosisOf,
  fieldLabel,
  isoToday,
  openCase,
  PROGRESS_EVENT,
  processCase,
  REFUSALS,
  STALE_AFTER_DAYS,
  staleOn,
} from '../plugin.js';
import { byArea, casePaneOf, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const CASE = 'case_0123456789abcdef';
const EXTRACT = 'job_0123456789abcdef';
const DIAGNOSE = 'job_fedcba9876543210';
const at = { status: 3, process: 4, fields: 10, diagnose: 11, deadline: 12, diagnosis: 13 };

const read = (value) => ({ value, status: 'extracted' });
const unreadable = { value: null, status: 'unreadable' };

const DIAGNOSIS = {
  denial_reason: 'prior_authorization',
  appeal_likelihood: 'high',
  likelihood_reasons: [
    'The payer denied the line for a missing authorization (CO-197).',
    'Payers often accept a retroactive authorization with the medical records.',
  ],
  codes: ['CO-197', 'N286'],
  extraction_digest: '0'.repeat(64),
  diagnosed_at: '2026-10-31T12:00:00Z',
};

/** A case body as `GET /cases/{id}` returns it. */
function caseBody({ claimId = read('CLAIM-77'), diagnosis = null, stale = false } = {}) {
  return {
    ok: true,
    case_id: CASE,
    documents: [{ doc_id: 'src_0', kind: 'edi_835', filename: null }],
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
    diagnosis,
    diagnosis_stale: stale,
  };
}

/** A worker that extracts on Process and diagnoses on Diagnose, as plugin_api does. */
function backend({ claimId = read('CLAIM-77') } = {}) {
  const state = { body: caseBody({ claimId }), calls: [] };
  const rest = async (path) => {
    state.calls.push(path);
    if (path === `/cases/${CASE}/process`) {
      return { ok: true, case_id: CASE, job_id: EXTRACT, kind: 'extract' };
    }
    if (path === `/cases/${CASE}/diagnose`) {
      state.body = caseBody({ claimId, diagnosis: DIAGNOSIS });
      return { ok: true, case_id: CASE, job_id: DIAGNOSE, kind: 'diagnose' };
    }
    if (path === `/cases/${CASE}`) return state.body;
    return { ok: true, status: 'ok', version: '0.1.0' };
  };
  return { rest, state };
}

/** A Hermes `ctx.rest` rejection carrying an envelope code. */
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'x' } })}`);

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

const latest = () => hooks.states[0].updates.at(-1);

afterEach(runCleanups);

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-6.1 appeal likelihood includes reasons', () => {
  test('test_us_6_1_pane_likelihood_includes_reasons', async () => {
    const api = createCaseApi(async () => caseBody({ diagnosis: DIAGNOSIS }));
    const ready = await openCase(api, CASE);
    assert.deepEqual(ready.diagnosis, {
      reason: 'prior_authorization',
      likelihood: 'high',
      reasons: DIAGNOSIS.likelihood_reasons,
      codes: ['CO-197', 'N286'],
      stale: false,
      checklist: [],
      cards: [],
      payerRead: true,
    });
    const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
    const panel = pane.props.children[at.diagnosis];
    assert.equal(panel.props['aria-label'], 'Diagnosis');
    const [reason, codes, likelihood, why, note] = panel.props.children;
    assert.equal(reason.props.children, 'Denial reason: Prior authorization or referral');
    assert.equal(codes.props.children, 'Codes: CO-197, N286');
    assert.equal(likelihood.props.children, 'Appeal likelihood: High');
    const reasons = why.props.children.map((li) => li.props.children);
    assert.ok(reasons.length >= 1);
    assert.deepEqual(reasons, DIAGNOSIS.likelihood_reasons);
    assert.equal(note, null, 'a current diagnosis is not flagged');
    assert.equal(pane.props.children[at.deadline], null, 'a case without a deadline shows none');
  });

  test('every backend label has a name; a case without diagnosis shows none', async () => {
    assert.deepEqual(Object.keys(DENIAL_REASONS), [
      'eligibility',
      'prior_authorization',
      'medical_necessity',
      'coding_error',
      'missing_information',
      'duplicate_claim',
      'timely_filing',
      'non_covered_service',
      'bundling',
      'coordination_of_benefits',
      'other',
    ]);
    assert.equal(DiagnosisPanel(undefined), null);
    const ready = await openCase(
      createCaseApi(async () => caseBody()),
      CASE,
    );
    assert.equal('diagnosis' in ready, false);
    const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
    assert.equal(pane.props.children[at.diagnosis], null);
  });

  test('diagnosisOf keeps only well-formed diagnoses', () => {
    const of = (changes, outer = {}) =>
      diagnosisOf({ diagnosis: { ...DIAGNOSIS, ...changes }, ...outer });
    assert.equal(diagnosisOf(null), null);
    assert.equal(diagnosisOf({ diagnosis: null }), null);
    assert.equal(of({ denial_reason: 'fraud' }), null);
    assert.equal(of({ denial_reason: 'toString' }), null, 'only own labels');
    assert.equal(of({ denial_reason: 7 }), null);
    assert.equal(of({ appeal_likelihood: 'certain' }), null);
    assert.equal(of({ appeal_likelihood: null }), null);
    assert.equal(of({ likelihood_reasons: [] }), null);
    assert.equal(of({ likelihood_reasons: 'Because.' }), null);
    assert.deepEqual(of({ likelihood_reasons: ['Kept.', 3] }).reasons, ['Kept.']);
    assert.deepEqual(of({ codes: undefined }).codes, []);
    assert.equal(of({}, { diagnosis_stale: 'yes' }).stale, false);
    const panel = DiagnosisPanel(of({ codes: [], appeal_likelihood: 'low' }));
    assert.equal(panel.props.children[1].props.children, 'Codes: none read');
    assert.equal(panel.props.children[2].props.children, 'Appeal likelihood: Low');
  });
});

describe('US-6.1 the pane diagnoses after extraction', () => {
  test('test_us_6_1_pane_diagnoses_after_extraction', async () => {
    const { rest, state } = backend();
    const { ctx, element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    const pane = rerender(element, ready, life());

    pane.props.children[at.process].props.onClick();
    await tick();
    assert.deepEqual(latest(), { state: 'processing', caseId: CASE, progress: 0 });
    ctx.emit(PROGRESS_EVENT, {
      case_id: CASE,
      job_id: EXTRACT,
      stage: 'extracting',
      progress: 0.5,
    });
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: EXTRACT, stage: 'done', progress: 1 });
    await tick();
    await tick();
    assert.ok(state.calls.includes(`/cases/${CASE}/diagnose`), 'every field read: diagnose');
    assert.deepEqual(latest(), {
      state: 'processing',
      caseId: CASE,
      progress: 0,
      diagnosing: true,
    });

    ctx.emit(PROGRESS_EVENT, {
      case_id: CASE,
      job_id: DIAGNOSE,
      stage: 'classifying',
      progress: 0,
    });
    const classifying = latest();
    assert.deepEqual(classifying, {
      state: 'processing',
      caseId: CASE,
      progress: 0,
      diagnosing: true,
    });
    assert.match(describeCase(classifying), /^Diagnosing case .* 0%$/);

    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: DIAGNOSE, stage: 'done', progress: 1 });
    await tick();
    const done = latest();
    assert.equal(done.state, 'ready');
    assert.equal(done.diagnosis.likelihood, 'high');
    assert.equal(
      state.calls.filter((path) => path.endsWith('/diagnose')).length,
      1,
      'a finished diagnosis is not chained again',
    );
    assert.deepEqual(hostAccesses, [], 'events come through ctx.onEvent, never host (US-3.3)');
  });

  test('fields left to confirm wait for the biller before any diagnosis', async () => {
    const { rest, state } = backend({ claimId: unreadable });
    const settled = await afterExtraction(createCaseApi(rest), CASE);
    assert.equal(settled.state, 'ready');
    assert.equal(state.calls.includes(`/cases/${CASE}/diagnose`), false);
    assert.match(
      describeCase(settled),
      /1 field\(s\) need confirmation; confirm them, then diagnose/,
    );

    const unavailable = await afterExtraction(
      createCaseApi(async () => {
        throw new Error('503: down');
      }),
      CASE,
    );
    assert.deepEqual(unavailable, { state: 'unavailable' });
    const empty = { ...caseBody(), extraction: null };
    const nothing = await afterExtraction(
      createCaseApi(async () => empty),
      CASE,
    );
    assert.deepEqual(nothing.fields, [], 'no fields: nothing to diagnose');
  });

  test('Diagnose case starts a diagnosis and explains a refusal', async () => {
    const { rest, state } = backend();
    const ready = await openCase(createCaseApi(rest), CASE);
    const element = { type: CasePane, props: { rest } };
    const pane = rerender(element, ready, life());
    const button = pane.props.children[at.diagnose];
    assert.equal(button.props.children, 'Diagnose case');
    assert.equal(button.props.disabled, false);
    button.props.onClick();
    await tick();
    assert.deepEqual(state.calls.at(-1), `/cases/${CASE}/diagnose`);
    assert.deepEqual(latest(), {
      state: 'processing',
      caseId: CASE,
      progress: 0,
      diagnosing: true,
    });
    assert.equal(hooks.states[1].value.processing, CASE, 'the pane follows the job');

    const refusing = async (path) => {
      if (path.endsWith('/diagnose')) throw rejection(409, 'not_extracted');
      return caseBody();
    };
    const refused = await diagnoseCase(createCaseApi(refusing), CASE);
    assert.equal(refused.notice, 'not_extracted');
    assert.match(describeCase(refused), new RegExp(REFUSALS.not_extracted.replace(/[.]/g, '\\.')));
    const failing = async () => {
      throw new Error('502: gateway');
    };
    assert.deepEqual(await diagnoseCase(createCaseApi(failing), CASE), { state: 'unavailable' });
  });

  test('Diagnose case is off without fields or an open case', () => {
    const element = { type: CasePane, props: { rest: async () => ({}) } };
    const empty = rerender(element, { state: 'ready', caseId: CASE, documents: [], fields: [] });
    assert.equal(empty.props.children[at.diagnose].props.disabled, true);
    const partial = rerender(element, { state: 'ready', caseId: CASE, documents: [] });
    assert.equal(partial.props.children[at.diagnose].props.disabled, true);
    const idle = rerender(element);
    assert.equal(idle.props.children[at.diagnose].props.disabled, true);
    idle.props.children[at.diagnose].props.onClick();
    assert.deepEqual(hooks.states[0].updates, [], 'nothing starts without a ready case');
  });

  test('a diagnosis joining a running extraction follows it as an extraction', async () => {
    const joining = async () => ({ ok: true, case_id: CASE, job_id: EXTRACT, kind: 'extract' });
    const joined = await diagnoseCase(createCaseApi(joining), CASE);
    assert.deepEqual(joined, { state: 'processing', caseId: CASE, progress: 0 });
    const legacy = await processCase(
      createCaseApi(async () => ({ ok: true })),
      CASE,
    );
    assert.deepEqual(legacy, { state: 'processing', caseId: CASE, progress: 0 });
  });

  test('a failed diagnosis reopens the case with its fixed explanation', async () => {
    for (const [code, notice] of [
      ['model_unavailable', 'model_unavailable'],
      ['diagnosis_failed', 'diagnosis_failed'],
      [null, 'diagnosis_failed'],
      ['internal_error', 'diagnosis_failed'],
    ]) {
      const { rest } = backend();
      const { ctx, element } = mounted(rest);
      const ready = await openCase(createCaseApi(rest), CASE);
      const pane = rerender(element, ready, life());
      pane.props.children[at.diagnose].props.onClick();
      await tick();
      ctx.emit(PROGRESS_EVENT, {
        case_id: CASE,
        job_id: DIAGNOSE,
        stage: 'failed',
        progress: 0,
        error_code: code,
      });
      await tick();
      assert.equal(latest().notice, notice);
      assert.equal(hooks.states[1].value.kind, 'extract');
      runCleanups();
    }
  });
});

describe('US-6.1 a confirmed field makes the diagnosis stale', () => {
  test('test_us_6_1_pane_flags_stale_diagnosis', async () => {
    const api = createCaseApi(async () => caseBody({ diagnosis: DIAGNOSIS, stale: true }));
    const ready = await openCase(api, CASE);
    assert.equal(ready.diagnosis.stale, true);
    assert.match(
      describeCase(ready),
      /The fields changed since the diagnosis; diagnose the case again\.$/,
    );
    const panel = DiagnosisPanel(ready.diagnosis);
    assert.equal(panel.props['data-stale'], true);
    assert.equal(panel.props.children[4].props.role, 'note');
    assert.match(panel.props.children[4].props.children, /Out of date/);
  });
});

const EXPLAINED = {
  ...DIAGNOSIS,
  explanation: {
    explanation: 'The payer refused the visit because no authorization was on file.',
    root_cause: 'The authorization was not requested before the visit.',
  },
  checklist: [
    { document: 'Copy of the denial notice or remittance', why: 'The appeal must cite it.' },
    { document: 'Medical records for the date of service', why: null },
  ],
  rule_cards: [
    {
      key: 'ACME Health/appeal_levels',
      payer: 'ACME Health',
      topic: 'appeal_levels',
      source: 'ACME Health provider manual',
      verified_on: '2026-10-01',
      stale: false,
    },
    {
      key: 'ACME Health/required_docs',
      payer: 'ACME Health',
      topic: 'required_docs',
      source: 'ACME Health provider manual',
      verified_on: '2026-03-01',
      stale: true,
    },
  ],
};

async function explainedPanel(diagnosis = EXPLAINED) {
  const ready = await openCase(
    createCaseApi(async () => caseBody({ diagnosis })),
    CASE,
  );
  const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
  return { ready, panel: pane.props.children[at.diagnosis] };
}

describe('US-6.2 explanation and root cause are shown', () => {
  test('test_us_6_2_pane_explanation_and_root_cause_shown', async () => {
    const { ready, panel } = await explainedPanel();
    assert.deepEqual(ready.diagnosis.explanation, {
      text: 'The payer refused the visit because no authorization was on file.',
      rootCause: 'The authorization was not requested before the visit.',
    });
    const explanation = panel.props.children[5];
    assert.equal(explanation.props['aria-label'], 'Explanation');
    const [text, rootCause] = explanation.props.children;
    assert.equal(text.props.children, EXPLAINED.explanation.explanation);
    assert.equal(
      rootCause.props.children,
      'Likely root cause: The authorization was not requested before the visit.',
    );
  });

  test('a diagnosis whose explanation did not run shows no explanation or checklist', async () => {
    const { ready, panel } = await explainedPanel({ ...EXPLAINED, explanation: null });
    assert.equal('explanation' in ready.diagnosis, false);
    assert.equal(panel.props.children[5], null);
    assert.equal(panel.props.children[6], null);
    const half = diagnosisOf({ diagnosis: { ...EXPLAINED, explanation: { explanation: 'x' } } });
    assert.equal('explanation' in half, false, 'a root cause is required');
  });
});

describe('US-6.2 checklist lists missing documentation', () => {
  test('test_us_6_2_pane_checklist_lists_missing_docs', async () => {
    const { ready, panel } = await explainedPanel();
    assert.deepEqual(ready.diagnosis.checklist, [
      { document: 'Copy of the denial notice or remittance', why: 'The appeal must cite it.' },
      { document: 'Medical records for the date of service', why: null },
    ]);
    const section = panel.props.children[6];
    assert.equal(section.props['aria-label'], 'Missing documentation');
    const [heading, checklist, cards] = section.props.children;
    assert.equal(heading.props.children, 'Missing documentation');
    assert.deepEqual(
      checklist.props.children.map((li) => li.props.children),
      [
        'Copy of the denial notice or remittance: The appeal must cite it.',
        'Medical records for the date of service',
      ],
    );
    assert.deepEqual(
      cards.props.children.map((li) => [li.props['data-stale'], li.props.children]),
      [
        [false, 'ACME Health/appeal_levels: ACME Health provider manual, verified 2026-10-01'],
        [
          true,
          'ACME Health/required_docs: ACME Health provider manual, verified 2026-03-01 ' +
            '(stale: check that it is still current)',
        ],
      ],
    );
  });

  test('cards without required documents say so; malformed entries are dropped', async () => {
    const { panel } = await explainedPanel({ ...EXPLAINED, checklist: [] });
    const [, empty] = panel.props.children[6].props.children;
    assert.equal(empty.props.children, "The payer's rule cards list no required documents.");
    const view = diagnosisOf({
      diagnosis: {
        ...EXPLAINED,
        checklist: [{ document: 'Kept', why: 3 }, { why: 'no document' }, null],
        rule_cards: [
          { key: 'k', source: 's' },
          null,
          'x',
          { ...EXPLAINED.rule_cards[0], stale: 'yes' },
        ],
      },
    });
    assert.deepEqual(view.checklist, [{ document: 'Kept', why: null }]);
    assert.deepEqual(view.cards, [
      {
        key: 'ACME Health/appeal_levels',
        source: 'ACME Health provider manual',
        verifiedOn: '2026-10-01',
        stale: false,
      },
    ]);
    assert.deepEqual(
      diagnosisOf({ diagnosis: { ...EXPLAINED, checklist: 'x', rule_cards: 7 } }).cards,
      [],
    );
  });
});

describe('US-6.2 no rule card for the payer', () => {
  test('test_us_6_2_pane_says_no_rule_card', async () => {
    const { panel } = await explainedPanel({ ...EXPLAINED, checklist: [], rule_cards: [] });
    const note = panel.props.children[6];
    assert.equal(note.props.role, 'note');
    assert.match(note.props.children, /^No rule card is on file for this payer/);
    assert.equal(
      ChecklistPanel(diagnosisOf({ diagnosis: EXPLAINED })).props['aria-label'],
      'Missing documentation',
    );
  });
});

describe('US-6.1 review regressions', () => {
  /** A backend whose `/diagnose` answer waits for `release()`. */
  function gatedDiagnose() {
    const { rest, state } = backend();
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const gated = async (path, opts) => {
      if (path.endsWith('/diagnose')) {
        state.calls.push(path);
        await gate;
        return { ok: true, case_id: CASE, job_id: DIAGNOSE, kind: 'diagnose' };
      }
      return rest(path, opts);
    };
    return { rest: gated, state, release: () => release() };
  }

  test('a chained diagnosis that ends before its start is answered still ends the wait', async () => {
    const { rest, state, release } = gatedDiagnose();
    const { ctx, element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    const pane = rerender(element, ready, life());
    pane.props.children[at.process].props.onClick();
    await tick();
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: EXTRACT, stage: 'done', progress: 1 });
    await tick();
    await tick();
    assert.ok(state.calls.includes(`/cases/${CASE}/diagnose`), 'the diagnosis was requested');
    assert.equal(hooks.states[1].value.kind, 'diagnose', 'followed before the answer');
    // The classification model is missing: the job fails before the POST is answered.
    ctx.emit(PROGRESS_EVENT, {
      case_id: CASE,
      job_id: DIAGNOSE,
      stage: 'failed',
      progress: 0,
      error_code: 'model_unavailable',
    });
    await tick();
    release();
    await tick();
    await tick();
    const last = latest();
    assert.equal(last.state, 'ready', 'never stuck at Diagnosing… 0%');
    assert.equal(last.notice, 'model_unavailable');
  });

  test('Diagnose case follows its own job before the start is answered', async () => {
    for (const [stage, code, expected] of [
      ['done', null, null],
      ['failed', 'internal_error', 'diagnosis_failed'],
    ]) {
      const { rest, state, release } = gatedDiagnose();
      const { ctx, element } = mounted(rest);
      const ready = await openCase(createCaseApi(rest), CASE);
      const pane = rerender(element, ready, life());
      pane.props.children[at.diagnose].props.onClick();
      await tick();
      ctx.emit(PROGRESS_EVENT, {
        case_id: CASE,
        job_id: DIAGNOSE,
        stage,
        progress: 1,
        error_code: code,
      });
      await tick();
      release();
      await tick();
      await tick();
      assert.equal(
        state.calls.filter((path) => path.endsWith('/diagnose')).length,
        1,
        'an early done is not taken for an extraction',
      );
      assert.equal(latest().state, 'ready');
      assert.equal(latest().notice, expected ?? undefined);
      runCleanups();
    }
  });

  test('Process after a Refresh during a diagnosis follows an extraction', async () => {
    const { rest, state } = backend();
    const { ctx, element } = mounted(rest);
    const ready = await openCase(createCaseApi(rest), CASE);
    const diagnosing = { ...life(), processing: CASE, kind: 'diagnose' };
    const pane = rerender(element, ready, diagnosing);
    pane.props.children[9].props.onClick(); // Refresh case
    assert.equal(diagnosing.kind, 'extract');
    pane.props.children[at.process].props.onClick();
    assert.equal(diagnosing.kind, 'extract');
    await tick();
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: EXTRACT, stage: 'done', progress: 1 });
    await tick();
    await tick();
    assert.ok(state.calls.includes(`/cases/${CASE}/diagnose`), 'the extraction is chained');
  });

  test('New case before the chained diagnosis starts it nowhere', async () => {
    const { rest, state } = backend();
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const slowOpen = async (path, opts) => {
      if (path === `/cases/${CASE}`) await gate;
      return rest(path, opts);
    };
    const { ctx, element } = mounted(slowOpen);
    const ready = await openCase(createCaseApi(rest), CASE);
    const remembered = { ...life(), processing: CASE };
    const pane = rerender(element, ready, remembered);
    ctx.emit(PROGRESS_EVENT, { case_id: CASE, job_id: EXTRACT, stage: 'done', progress: 1 });
    pane.props.children[5].props.onClick(); // New case
    release();
    await tick();
    await tick();
    assert.equal(state.calls.includes(`/cases/${CASE}/diagnose`), false);
    assert.equal(remembered.processing, null);
    assert.deepEqual(latest(), { state: 'idle' });
  });
});

test('afterExtraction alone diagnoses a fully read case', async () => {
  const { rest, state } = backend();
  const next = await afterExtraction(createCaseApi(rest), CASE);
  assert.deepEqual(next, { state: 'processing', caseId: CASE, progress: 0, diagnosing: true });
  assert.ok(state.calls.includes(`/cases/${CASE}/diagnose`));
});

const DEADLINE = {
  status: 'computed',
  due: '2027-04-13',
  denial_date: '2026-10-15',
  limit_days: 180,
  rule_card: 'ACME Health/appeal_levels',
};

/** The deadline as a case body carries it, read with the case (US-6.3). */
const deadlineOfCase = async (deadline) => {
  const body = { ...caseBody(), deadline };
  return (
    await openCase(
      createCaseApi(async () => body),
      CASE,
    )
  ).deadline;
};

describe('US-6.3 deadline is computed from the rule card', () => {
  test('test_us_6_3_pane_deadline_from_rule_card', async () => {
    const deadline = await deadlineOfCase(DEADLINE);
    assert.deepEqual(deadline, {
      status: 'computed',
      due: '2027-04-13',
      denialDate: '2026-10-15',
      limitDays: 180,
      card: 'ACME Health/appeal_levels',
    });
    const line = DeadlineLine(deadline, '2026-10-31');
    assert.equal(line.props['aria-label'], 'Appeal deadline');
    assert.equal(
      line.props.children,
      'Appeal by 2027-04-13: 180 days from the denial date 2026-10-15 (ACME Health/appeal_levels ' +
        'rule card).',
    );
    assert.equal(line.props['data-passed'], false);
    assert.equal(line.props.style, undefined);
    // The pane shows it with the case, diagnosed or not, judged with this Mac's date.
    const ready = await openCase(
      createCaseApi(async () => ({ ...caseBody(), deadline: DEADLINE })),
      CASE,
    );
    const pane = rerender({ type: CasePane, props: { rest: async () => ({}) } }, ready, life());
    assert.equal(pane.props.children[at.deadline].props['data-status'], 'computed');
    assert.equal(pane.props.children[at.diagnosis], null, 'no diagnosis needed for a deadline');
  });

  test('the denial date is a field the biller confirms', () => {
    assert.equal(fieldLabel('denial_date'), 'Denial date');
  });

  test("isoToday reads this Mac's calendar date", () => {
    assert.equal(isoToday(new Date(2026, 0, 5, 23, 59)), '2026-01-05');
    assert.match(isoToday(), /^\d{4}-\d{2}-\d{2}$/);
  });
});

describe('US-6.3 the deadline has passed', () => {
  test('test_us_6_3_pane_flags_passed_deadline', async () => {
    const deadline = await deadlineOfCase(DEADLINE);
    const onTheDay = describeDeadline(deadline, '2027-04-13');
    assert.equal(onTheDay.passed, false, 'the due date itself is still in time');
    const line = DeadlineLine(deadline, '2027-04-14');
    assert.equal(line.props['data-passed'], true);
    assert.match(line.props.children, /This deadline has passed\.$/);
    assert.deepEqual(line.props.style, { color: '#b91c1c', fontWeight: 600 });
  });
});

describe('US-6.3 an unknown deadline says why', () => {
  test('test_us_6_3_pane_unknown_deadline_says_why', async () => {
    for (const status of [
      'no_payer',
      'no_rule_card',
      'no_appeal_limit',
      'no_denial_date',
      'implausible_denial_date',
    ]) {
      const deadline = await deadlineOfCase({ status, due: null, denial_date: null });
      assert.equal(deadline.status, status);
      const line = DeadlineLine(deadline, '2026-10-31');
      assert.equal(line.props.children, DEADLINE_UNKNOWN[status]);
      assert.equal(line.props['data-passed'], false);
    }
    assert.match(DEADLINE_UNKNOWN.no_denial_date, /confirm the denial date/);
    assert.match(DEADLINE_UNKNOWN.no_payer, /confirm the payer/);
    assert.match(
      DEADLINE_UNKNOWN.implausible_denial_date,
      /after today or before the date of service/,
    );
  });

  test('malformed deadlines are dropped', async () => {
    assert.equal(await deadlineOfCase({ status: 'soon' }), undefined);
    assert.equal(await deadlineOfCase({ status: 'computed', due: null }), undefined);
    assert.equal(await deadlineOfCase({ status: 'toString' }), undefined, 'only own reasons');
    assert.equal(await deadlineOfCase(null), undefined);
    assert.deepEqual(
      await deadlineOfCase({ status: 'no_rule_card', limit_days: '180', rule_card: 7 }),
      { status: 'no_rule_card', due: null, denialDate: null, limitDays: null, card: null },
    );
    assert.equal(DeadlineLine(undefined, '2026-10-31'), null);
  });
});

describe('US-6.2 review regressions', () => {
  test('an unreadable payer asks the biller to confirm it, not the manager to add a card', async () => {
    const body = caseBody({ diagnosis: { ...EXPLAINED, checklist: [], rule_cards: [] } });
    body.extraction.payer_name = { value: null, status: 'unreadable' };
    const ready = await openCase(
      createCaseApi(async () => body),
      CASE,
    );
    assert.equal(ready.diagnosis.payerRead, false);
    const note = ChecklistPanel(ready.diagnosis, '2026-10-31');
    assert.match(note.props.children, /^The payer could not be read.*confirm the payer/);
    assert.equal(diagnosisOf({ diagnosis: EXPLAINED }).payerRead, false, 'no extraction: unread');
  });

  test('a card that became stale after the diagnosis is flagged today', () => {
    assert.equal(STALE_AFTER_DAYS, 180);
    assert.equal(staleOn('2026-05-04', '2026-10-31'), false, '180 days: still current');
    assert.equal(staleOn('2026-05-03', '2026-10-31'), true, '181 days: stale');
    const view = diagnosisOf({ diagnosis: EXPLAINED });
    const later = ChecklistPanel(view, '2027-06-01');
    const [, , cards] = later.props.children;
    assert.deepEqual(
      cards.props.children.map((li) => li.props['data-stale']),
      [true, true],
      'the stored flag was false for the first card; today it is stale',
    );
    assert.equal(ChecklistPanel(view).props['aria-label'], 'Missing documentation');
  });
});
