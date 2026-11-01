// @ts-check
/**
 * ClaimCoach desktop half: case pane, manager dashboard route, local-only statusbar item, and
 * settings page. Plain ESM, no build step, no JSX (PC-3).
 *
 * Implements: US-1.1 (package layout), US-1.4 (registration contract and allowed imports), US-3.3
 * (the case API client wraps only `ctx.rest`; the pane never touches `host`, the composer, or
 * agent sessions), US-3.5 (the statusbar item shows when richer agent access is on), US-5.1 (the
 * pane is a drop zone, has a paste box, lists the case's source documents, and adds to the open
 * case), US-5.2 (progress arrives as `plugin.claimcoach.case.progress` through `ctx.onEvent`; the
 * extracted fields are listed with unreadable ones highlighted, and the biller confirms values),
 * US-6.1 (an extraction that left nothing to confirm starts the diagnosis; the pane shows the
 * denial reason and the appeal likelihood with its reasons, flags a stale diagnosis, and has a
 * Diagnose case button), US-6.2 (the explanation, the likely root cause, the missing-documentation
 * checklist with each item's reason, and the rule cards it came from, flagged when stale), US-6.3
 * (the case's appeal deadline, read with the case, with its limit, denial date, and card, flagged
 * once passed, or why it is unknown; the denial date is a field the biller confirms), US-7.1 (a
 * Draft appeal button once the case is diagnosed; drafting progress; the draft under the heading
 * "Draft for human review", with the template and rule cards it came from, flagged when stale),
 * US-7.2 (the draft in an editor with Save draft, Export PDF, and Export DOCX; an export is saved
 * through the host's save dialog, where the biller picks the folder), US-7.3 (no contribution or
 * control sends, submits, faxes, e-mails, or uploads anything to a payer), US-8.1 (an Outcome
 * section marks the case overturned, upheld, or written off, which closes it after the biller
 * confirms; the recorded outcome shows with the case, and a closed case's editing controls are
 * disabled), US-8.2 (the manager dashboard shows the last completed week's de-identified outcome
 * summary of the profiles that share their outcomes: counts and overturn rate per payer and denial
 * reason), US-8.3 (the dashboard's fine-tune export runs only after the manager types their
 * name and ticks the approval; it says where the de-identified file was written).
 * Rules: PC-1 (opt-in: `defaultEnabled: false`), PC-3 (imports only
 * `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`; optional SDK calls are feature-detected),
 * PC-4, BR-2 (case data goes pane → `ctx.rest` → plugin_api → worker, never the agent transcript),
 * BR-4 (every draft is shown labeled "draft for human review"; there is no send or submit control
 * anywhere, and nothing is sent: an export is a file the biller saves), BR-14 (error text from the backend is never shown; a refusal shows a fixed message per code).
 *
 * EPIC-10 (US-10.1..US-10.3) builds the views out; the pane and settings page already show the
 * worker status so a user can tell whether the backend half is enabled.
 */
import * as sdk from '@hermes/plugin-sdk';
import { useEffect, useState } from 'react';
import { jsx, jsxs } from 'react/jsx-runtime';

export const PLUGIN_ID = 'claimcoach';
export const DASHBOARD_PATH = '/claimcoach/dashboard';
/** How often the statusbar re-reads `/settings` (US-3.5). */
export const SETTINGS_REFRESH_MS = 15_000;

/**
 * @typedef {import('@hermes/plugin-sdk').PluginRestOptions} RestOptions
 * @typedef {(path: string, opts?: RestOptions) => Promise<unknown>} RestFn
 * @typedef {{ ok: true, status: 'ok', version: string }} HealthResponse
 * @typedef {{ state: 'loading' } | { state: 'ok', version: string } | { state: 'unavailable' }} WorkerState
 * @typedef {{ filename: string, contentType: string, bytes: ArrayBuffer }} DocumentUpload
 * @typedef {{ name: string, type: string, size?: number, arrayBuffer: () => Promise<ArrayBuffer> }} PickedFile
 * @typedef {keyof typeof REFUSALS} Refusal
 * @typedef {{ docId: string, kind: string, label: string }} DocumentView
 * @typedef {'extracted' | 'unreadable' | 'confirmed'} FieldStatus
 * @typedef {{ path: string, label: string, value: string, status: FieldStatus }} FieldView
 * @typedef {'low' | 'medium' | 'high'} Likelihood
 * @typedef {keyof typeof DENIAL_REASONS} DenialReason
 * @typedef {{ text: string, rootCause: string }} ExplanationView
 * @typedef {{ document: string, why: string | null }} ChecklistView
 * @typedef {{ key: string, source: string, verifiedOn: string, stale: boolean }} RuleCardView
 * @typedef {'computed' | 'no_payer' | 'no_rule_card' | 'no_appeal_limit' | 'no_denial_date'
 *   | 'implausible_denial_date'} DeadlineStatus
 * @typedef {{ status: DeadlineStatus, due: string | null, denialDate: string | null,
 *   limitDays: number | null, card: string | null }} DeadlineView
 * @typedef {{ reason: DenialReason, likelihood: Likelihood, reasons: string[], codes: string[],
 *   stale: boolean, explanation?: ExplanationView, checklist: ChecklistView[],
 *   cards: RuleCardView[], payerRead: boolean }} DiagnosisView
 * @typedef {{ text: string, templateId: string, ruleCards: string[], stale: boolean,
 *   edited: boolean }} DraftView
 * @typedef {keyof typeof OUTCOMES} Outcome
 * @typedef {{ outcome: Outcome, recordedAt: string }} OutcomeView
 * @typedef {{ overturned: number, upheld: number, writtenOff: number, total: number,
 *   rate: number | null }} CountsView
 * @typedef {CountsView & { payer: string | null, reason: DenialReason | null }} CategoryView
 * @typedef {CountsView & { payer: string | null, code: string }} CodeView
 * @typedef {{ week: string, timezone: string, profiles: string[], notShared: number,
 *   unreadable: number, totals: CountsView, categories: CategoryView[],
 *   codes: CodeView[] }} SummaryView
 * @typedef {{ state: 'loading' } | { state: 'ok', summary: SummaryView }
 *   | { state: 'unavailable' }} SummaryState
 * @typedef {{ state: 'exporting' } | { state: 'written', path: string, records: number }
 *   | { state: 'refused' } | { state: 'failed' }} FineTuneResult
 * @typedef {{ state: 'ready', caseId: string, documents: DocumentView[], fields: FieldView[],
 *   otherClaims?: number, unreadSources?: number, notice?: Refusal,
 *   diagnosis?: DiagnosisView, deadline?: DeadlineView, draft?: DraftView,
 *   outcome?: OutcomeView, closed?: true }} ReadyState
 * @typedef {'extract' | 'diagnose' | 'draft'} JobKind
 * @typedef {{ state: 'idle', notice?: Refusal } | { state: 'busy' } | ReadyState
 *   | { state: 'processing', caseId: string, progress: number, diagnosing?: true,
 *       drafting?: true }
 *   | { state: 'unavailable', caseId?: string }} CaseState
 * @typedef {'pdf' | 'docx'} ExportFormat
 * @typedef {(path: string, suggestedName: string) => Promise<void>} SaveFile
 * @typedef {{ state: 'exporting', format: ExportFormat } | { state: 'saved', format: ExportFormat }
 *   | { state: 'written', format: ExportFormat, path: string, expiresAt: string }
 *   | { state: 'refused', notice: Refusal } | { state: 'failed' }} ExportResult
 * @typedef {{ caseId: string, stage: string, progress: number, errorCode: string | null }} Progress
 * @typedef {(listener: (payload: unknown) => void) => () => void} SubscribeFn
 */

/** Largest file the backend accepts (US-5.1); bigger ones are refused before they are read. */
export const MAX_FILE_BYTES = 16 * 1024 * 1024;

/** Wire name of the worker's progress events (US-5.2, PC-4). */
export const PROGRESS_EVENT = 'plugin.claimcoach.case.progress';

/** Fixed text per code the pane explains (BR-14: never the backend's own text). */
export const REFUSALS = Object.freeze({
  document_too_large: 'That file is too large. ClaimCoach accepts files up to 16 MiB.',
  unsupported_document: 'ClaimCoach reads PDF, PNG, JPEG, and plain-text documents only.',
  case_closed: 'This case is closed, so it takes no new documents or changes.',
  no_documents: 'Add a source document before processing the case.',
  invalid_value: 'That value is not valid for this field.',
  model_unavailable: 'The local model for this step is missing or not responding.',
  model_busy: 'The local models are busy; process the case again in a moment.',
  extraction_failed: 'The documents could not be read; enter the fields by hand.',
  worker_unavailable: 'The ClaimCoach worker stopped; start it and process the case again.',
  job_not_found: 'Processing stopped before it finished; process the case again.',
  processing_timeout: 'Processing took too long and was stopped; process the case again.',
  not_extracted: 'Process the case so its fields are read before diagnosing it.',
  diagnosis_failed:
    "The local model's answer could not be used; check the case's fields, then diagnose again.",
  not_diagnosed: 'Diagnose the case (again, if its fields changed) before drafting the appeal.',
  no_letter_template:
    'No appeal letter template is in the global corpus; ask the manager to import one.',
  drafting_failed: "The local model's draft could not be used; draft the appeal again.",
  not_drafted: 'Draft the appeal before saving or exporting it.',
  draft_edited:
    'The draft was edited while a new one was being drafted, so your edits were kept; draft ' +
    'again to replace them.',
  invalid_draft: 'The draft needs some text, and at most 20,000 characters.',
  outcome_busy: 'The case is being processed; record its outcome when that finishes.',
});

/** How a case can end, as the pane names it (US-8.1: the backend's `CaseOutcome`). */
export const OUTCOMES = Object.freeze({
  overturned: 'Overturned',
  upheld: 'Upheld',
  written_off: 'Written off',
});

/** The label every draft carries (BR-4); a draft the backend sends without it is not shown. */
export const DRAFT_LABEL = 'draft for human review';
/** Longest draft the backend stores (US-7.2). */
export const MAX_LETTER_CHARS = 20_000;

/** Denial reasons as the pane names them (US-6.1: the backend's closed set). */
export const DENIAL_REASONS = Object.freeze({
  eligibility: 'Eligibility or coverage',
  prior_authorization: 'Prior authorization or referral',
  medical_necessity: 'Medical necessity',
  coding_error: 'Coding error',
  missing_information: 'Missing information',
  duplicate_claim: 'Duplicate claim',
  timely_filing: 'Timely filing',
  non_covered_service: 'Service not covered',
  bundling: 'Bundled service',
  coordination_of_benefits: 'Coordination of benefits',
  other: 'Other',
});
const LIKELIHOODS = new Set(['low', 'medium', 'high']);

/** Why an appeal deadline is unknown, and what fixes it (US-6.3). */
export const DEADLINE_UNKNOWN = Object.freeze({
  no_payer: 'Appeal deadline unknown: confirm the payer, so its rule card can be found.',
  no_rule_card: 'Appeal deadline unknown: no rule card is on file for this payer.',
  no_appeal_limit: "Appeal deadline unknown: the payer's rule cards give no appeal time limit.",
  no_denial_date: 'Appeal deadline unknown: confirm the denial date.',
  implausible_denial_date:
    'Appeal deadline unknown: the denial date is after today or before the date of service; ' +
    'confirm it.',
});

/** Field and list names as the pane shows them. */
const FIELD_NAMES = Object.freeze({
  payer_name: 'Payer',
  claim_id: 'Claim number',
  billed_amount: 'Billed',
  paid_amount: 'Paid',
  denial_date: 'Denial date',
  adjustments: 'Adjustment',
  group_code: 'Group code',
  carc: 'CARC',
  amount: 'Amount',
  rarc_codes: 'RARC',
  lines: 'Line',
  procedure_code: 'Procedure code',
  service_date: 'Service date',
});
const FIELD_STATUSES = new Set(['extracted', 'unreadable', 'confirmed']);

/**
 * The pane's only way to reach case data: typed calls over `ctx.rest` to this plugin's own
 * backend (`/api/plugins/claimcoach/...`). Nothing here can reach the agent, the composer, or a
 * session (BR-2).
 *
 * @param {RestFn} rest
 */
export function createCaseApi(rest) {
  /** @param {string} caseId */
  const casePath = (caseId) => `/cases/${encodeURIComponent(caseId)}`;
  return {
    /** Create an empty case. */
    createCase: () => rest('/cases', { method: 'POST', body: {} }),
    /**
     * @param {string} caseId
     * @param {DocumentUpload} upload
     */
    uploadDocument: (caseId, upload) =>
      rest(`${casePath(caseId)}/documents`, { method: 'POST', upload }),
    /** @param {string} caseId */
    getCase: (caseId) => rest(casePath(caseId)),
    /**
     * @param {string} caseId
     * @param {string} text
     */
    pasteText: (caseId, text) =>
      rest(`${casePath(caseId)}/paste`, { method: 'POST', body: { text } }),
    /** @param {string} caseId */
    processCase: (caseId) => rest(`${casePath(caseId)}/process`, { method: 'POST', body: {} }),
    /** @param {string} caseId */
    diagnoseCase: (caseId) => rest(`${casePath(caseId)}/diagnose`, { method: 'POST', body: {} }),
    /** @param {string} caseId */
    draftCase: (caseId) => rest(`${casePath(caseId)}/draft`, { method: 'POST', body: {} }),
    /**
     * @param {string} caseId
     * @param {string} text
     */
    saveDraft: (caseId, text) =>
      rest(`${casePath(caseId)}/draft/text`, { method: 'POST', body: { text } }),
    /**
     * @param {string} caseId
     * @param {ExportFormat} format
     */
    exportDraft: (caseId, format) =>
      rest(`${casePath(caseId)}/export`, { method: 'POST', body: { format } }),
    /**
     * @param {string} caseId
     * @param {Outcome} outcome
     */
    recordOutcome: (caseId, outcome) =>
      rest(`${casePath(caseId)}/outcome`, { method: 'POST', body: { outcome } }),
    /**
     * @param {string} caseId
     * @param {string} path
     * @param {string} value
     */
    confirmField: (caseId, path, value) =>
      rest(`${casePath(caseId)}/fields`, { method: 'POST', body: { path, value } }),
  };
}

/** @typedef {ReturnType<typeof createCaseApi>} CaseApi */

/**
 * @param {unknown} body
 * @returns {string | null}
 */
function caseIdOf(body) {
  const id = /** @type {{ case_id?: unknown } | null} */ (body)?.case_id;
  return typeof id === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(id) ? id : null;
}

/**
 * The envelope code of a failed `ctx.rest` call. Hermes rejects with `"<status>: <body>"`; only
 * the envelope's code is read, never its message.
 *
 * @param {unknown} error
 * @returns {string | null}
 */
function codeOf(error) {
  const message = error instanceof Error ? error.message : '';
  const start = message.indexOf('{');
  if (start < 0) return null;
  try {
    const code = JSON.parse(message.slice(start))?.error?.code;
    return typeof code === 'string' ? code : null;
  } catch {
    return null;
  }
}

/**
 * @param {string | null | undefined} code
 * @returns {Refusal | null}
 */
function known(code) {
  return typeof code === 'string' && Object.hasOwn(REFUSALS, code)
    ? /** @type {Refusal} */ (code)
    : null;
}

/**
 * The refusal code of a failed `ctx.rest` call, when it is one the pane explains.
 *
 * @param {unknown} error
 * @returns {Refusal | null}
 */
export function refusalOf(error) {
  return known(codeOf(error));
}

/**
 * @param {string} path
 * @returns {string}
 */
export function fieldLabel(path) {
  const parts = path.split('.');
  const words = [];
  for (let i = 0; i < parts.length; i += 1) {
    const part = /** @type {string} */ (parts[i]);
    const name = FIELD_NAMES[/** @type {keyof typeof FIELD_NAMES} */ (part)] ?? part;
    const next = parts[i + 1];
    if (next !== undefined && /^\d+$/.test(next)) {
      words.push(`${name} ${Number(next) + 1}`);
      i += 1;
    } else {
      words.push(name);
    }
  }
  return words.join(' · ');
}

/**
 * Flatten a case's extraction into its fields, in document order.
 *
 * @param {unknown} node
 * @param {string} [path]
 * @returns {FieldView[]}
 */
export function fieldsOf(node, path = '') {
  if (Array.isArray(node)) return node.flatMap((item, i) => fieldsOf(item, `${path}.${i}`));
  if (node === null || typeof node !== 'object') return [];
  const field = /** @type {{ status?: unknown, value?: unknown }} */ (node);
  if (typeof field.status === 'string' && FIELD_STATUSES.has(field.status)) {
    const value = field.value === null || field.value === undefined ? '' : String(field.value);
    const status = /** @type {FieldStatus} */ (field.status);
    return path ? [{ path, label: fieldLabel(path), value, status }] : [];
  }
  return Object.entries(node).flatMap(([key, child]) =>
    key === 'sources' || key === 'other_claims'
      ? []
      : fieldsOf(child, path ? `${path}.${key}` : key),
  );
}

/**
 * @param {unknown} list
 * @returns {string[]}
 */
function stringsOf(list) {
  return Array.isArray(list) ? list.filter((item) => typeof item === 'string') : [];
}

/**
 * @param {unknown} value
 * @returns {ExplanationView | null}
 */
function explanationOf(value) {
  const explanation = /** @type {{ explanation?: unknown, root_cause?: unknown } | null} */ (value);
  const text = explanation?.explanation;
  const rootCause = explanation?.root_cause;
  return typeof text === 'string' && typeof rootCause === 'string' ? { text, rootCause } : null;
}

/**
 * @param {unknown} list
 * @returns {ChecklistView[]}
 */
function checklistOf(list) {
  if (!Array.isArray(list)) return [];
  return list.flatMap((entry) => {
    const item = /** @type {{ document?: unknown, why?: unknown } | null} */ (entry);
    if (typeof item?.document !== 'string') return [];
    return [{ document: item.document, why: typeof item.why === 'string' ? item.why : null }];
  });
}

/**
 * @param {unknown} list
 * @returns {RuleCardView[]}
 */
function cardsOf(list) {
  if (!Array.isArray(list)) return [];
  return list.flatMap((entry) => {
    const card =
      /** @type {{ key?: unknown, source?: unknown, verified_on?: unknown, stale?: unknown }
       *   | null} */ (entry);
    if (
      typeof card?.key !== 'string' ||
      typeof card.source !== 'string' ||
      typeof card.verified_on !== 'string'
    ) {
      return [];
    }
    return [
      {
        key: card.key,
        source: card.source,
        verifiedOn: card.verified_on,
        stale: card.stale === true,
      },
    ];
  });
}

/**
 * @param {unknown} value
 * @returns {string | null}
 */
function textOrNull(value) {
  return typeof value === 'string' ? value : null;
}

/**
 * @param {unknown} value
 * @returns {DeadlineView | null}
 */
function deadlineOf(value) {
  const deadline =
    /** @type {{ status?: unknown, due?: unknown, denial_date?: unknown, limit_days?: unknown,
     *   rule_card?: unknown } | null} */ (value);
  const status = deadline?.status;
  const known = status === 'computed' || Object.hasOwn(DEADLINE_UNKNOWN, String(status));
  if (!known || (status === 'computed' && typeof deadline?.due !== 'string')) return null;
  return {
    status: /** @type {DeadlineStatus} */ (status),
    due: textOrNull(deadline?.due),
    denialDate: textOrNull(deadline?.denial_date),
    limitDays: typeof deadline?.limit_days === 'number' ? deadline.limit_days : null,
    card: textOrNull(deadline?.rule_card),
  };
}

/**
 * Today on this Mac as `YYYY-MM-DD`, to compare with an ISO due date.
 *
 * @param {Date} [now]
 * @returns {string}
 */
export function isoToday(now = new Date()) {
  const pad = (/** @type {number} */ n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Days after which a rule card is stale (the backend's `STALE_AFTER_DAYS`, US-4.3). */
export const STALE_AFTER_DAYS = 180;

/**
 * Whether a card verified on `verifiedOn` is stale on `today`. The diagnosis stores the flag as
 * it was when the diagnosis ran; the pane judges it again for today.
 *
 * @param {string} verifiedOn `YYYY-MM-DD`
 * @param {string} today `YYYY-MM-DD`
 * @returns {boolean}
 */
export function staleOn(verifiedOn, today) {
  const noon = new Date(`${today}T12:00:00`);
  noon.setDate(noon.getDate() - STALE_AFTER_DAYS);
  return verifiedOn < isoToday(noon);
}

/**
 * The appeal deadline as the pane says it (US-6.3).
 *
 * @param {DeadlineView} deadline
 * @param {string} today `YYYY-MM-DD`
 * @returns {{ text: string, passed: boolean }}
 */
export function describeDeadline(deadline, today) {
  if (deadline.status !== 'computed') {
    return { text: DEADLINE_UNKNOWN[deadline.status], passed: false };
  }
  const passed = String(deadline.due) < today;
  const text =
    `Appeal by ${deadline.due}: ${deadline.limitDays} days from the denial date ` +
    `${deadline.denialDate} (${deadline.card} rule card).` +
    (passed ? ' This deadline has passed.' : '');
  return { text, passed };
}

/**
 * A case body's diagnosis, when it holds a well-formed one (US-6.1, US-6.2, US-6.3).
 *
 * @param {unknown} body
 * @returns {DiagnosisView | null}
 */
export function diagnosisOf(body) {
  const outer = /** @type {{ diagnosis?: unknown, diagnosis_stale?: unknown } | null} */ (body);
  const diagnosis = /** @type {{ denial_reason?: unknown, appeal_likelihood?: unknown,
   *   likelihood_reasons?: unknown, codes?: unknown, explanation?: unknown, checklist?: unknown,
   *   rule_cards?: unknown } | null | undefined} */ (outer?.diagnosis);
  const reason = diagnosis?.denial_reason;
  const likelihood = diagnosis?.appeal_likelihood;
  const reasons = stringsOf(diagnosis?.likelihood_reasons);
  if (
    typeof reason !== 'string' ||
    !Object.hasOwn(DENIAL_REASONS, reason) ||
    typeof likelihood !== 'string' ||
    !LIKELIHOODS.has(likelihood) ||
    reasons.length === 0
  ) {
    return null;
  }
  const payer = /** @type {{ extraction?: { payer_name?: { value?: unknown } } | null } | null} */ (
    body
  )?.extraction?.payer_name?.value;
  /** @type {DiagnosisView} */
  const view = {
    reason: /** @type {DenialReason} */ (reason),
    likelihood: /** @type {Likelihood} */ (likelihood),
    reasons,
    codes: stringsOf(diagnosis?.codes),
    stale: outer?.diagnosis_stale === true,
    checklist: checklistOf(diagnosis?.checklist),
    cards: cardsOf(diagnosis?.rule_cards),
    payerRead: typeof payer === 'string',
  };
  const explanation = explanationOf(diagnosis?.explanation);
  if (explanation) view.explanation = explanation;
  return view;
}

/**
 * A case body's appeal draft, when it holds a well-formed one carrying the review label (US-7.1).
 *
 * @param {unknown} body
 * @returns {DraftView | null}
 */
export function draftOf(body) {
  const outer = /** @type {{ draft?: unknown, draft_stale?: unknown } | null} */ (body);
  const draft = /** @type {{ label?: unknown, text?: unknown, template_id?: unknown,
   *   rule_cards?: unknown, edited_at?: unknown } | null | undefined} */ (outer?.draft);
  if (
    draft?.label !== DRAFT_LABEL ||
    typeof draft.text !== 'string' ||
    !draft.text.trim() ||
    typeof draft.template_id !== 'string'
  ) {
    return null;
  }
  return {
    text: draft.text,
    templateId: draft.template_id,
    ruleCards: stringsOf(draft.rule_cards),
    stale: outer?.draft_stale === true,
    edited: typeof draft.edited_at === 'string',
  };
}

/**
 * A case body's recorded outcome, when it holds a well-formed one (US-8.1).
 *
 * @param {unknown} body
 * @returns {OutcomeView | null}
 */
export function outcomeOf(body) {
  const outcome = /** @type {{ outcome?: { outcome?: unknown, recorded_at?: unknown } | null }
   *   | null} */ (body)?.outcome;
  const value = outcome?.outcome;
  if (typeof value !== 'string' || !Object.hasOwn(OUTCOMES, value)) return null;
  if (typeof outcome?.recorded_at !== 'string') return null;
  return { outcome: /** @type {Outcome} */ (value), recordedAt: outcome.recorded_at };
}

/**
 * The ready state for a case body.
 *
 * @param {string} caseId
 * @param {unknown} body
 * @returns {ReadyState}
 */
function readyFrom(caseId, body) {
  const extraction = /** @type {{ extraction?: { other_claims?: unknown } | null } | null} */ (body)
    ?.extraction;
  /** @type {ReadyState} */
  const ready = {
    state: 'ready',
    caseId,
    documents: documentsOf(body),
    fields: fieldsOf(extraction),
  };
  const others = extraction?.other_claims;
  if (typeof others === 'number' && others > 0) ready.otherClaims = others;
  const unread = /** @type {{ unread_sources?: unknown } | null | undefined} */ (extraction)
    ?.unread_sources;
  if (Array.isArray(unread) && unread.length > 0) ready.unreadSources = unread.length;
  const diagnosis = diagnosisOf(body);
  if (diagnosis) ready.diagnosis = diagnosis;
  const deadline = deadlineOf(/** @type {{ deadline?: unknown } | null} */ (body)?.deadline);
  if (deadline) ready.deadline = deadline;
  const draft = draftOf(body);
  if (draft) ready.draft = draft;
  const outcome = outcomeOf(body);
  if (outcome) ready.outcome = outcome;
  if (typeof (/** @type {{ closed_at?: unknown } | null} */ (body)?.closed_at) === 'string') {
    ready.closed = true;
  }
  return ready;
}

/**
 * Reopen the case and show a notice; a case that does not reopen reads as unavailable.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {Refusal} notice
 * @returns {Promise<CaseState>}
 */
export async function reopenWith(api, caseId, notice) {
  const reopened = await openCase(api, caseId);
  return reopened.state === 'ready' ? { ...reopened, notice } : reopened;
}

/**
 * A progress event's payload, when it is one (PC-4; US-3.4: IDs, a stage, a fraction, a code).
 *
 * @param {unknown} payload
 * @returns {Progress | null}
 */
export function progressOf(payload) {
  const event =
    /** @type {{ case_id?: unknown, stage?: unknown, progress?: unknown, error_code?: unknown } | null} */ (
      payload
    );
  if (
    typeof event?.case_id !== 'string' ||
    typeof event.stage !== 'string' ||
    typeof event.progress !== 'number'
  ) {
    return null;
  }
  const errorCode = typeof event.error_code === 'string' ? event.error_code : null;
  return { caseId: event.case_id, stage: event.stage, progress: event.progress, errorCode };
}

/**
 * @param {unknown} body
 * @returns {DocumentView[]}
 */
export function documentsOf(body) {
  const list = /** @type {{ documents?: unknown } | null} */ (body)?.documents;
  if (!Array.isArray(list)) return [];
  return list.flatMap((entry) => {
    const doc = /** @type {{ doc_id?: unknown, kind?: unknown, filename?: unknown }} */ (entry);
    if (typeof doc?.doc_id !== 'string' || typeof doc.kind !== 'string') return [];
    const pasted = doc.kind === 'edi_835' ? 'Pasted 835 text' : 'Pasted text';
    const label = typeof doc.filename === 'string' ? doc.filename : pasted;
    return [{ docId: doc.doc_id, kind: doc.kind, label }];
  });
}

/**
 * Add a document to the open case, creating the case first when none is open, then reopen it.
 * A refusal the pane explains keeps the case open with a notice. Any other failure reads as
 * `unavailable`, still naming the case once it exists, so the next document joins it.
 *
 * @param {CaseApi} api
 * @param {string | null} caseId
 * @param {(caseId: string) => Promise<unknown>} send
 * @returns {Promise<CaseState>}
 */
async function addDocument(api, caseId, send) {
  let id = caseId;
  try {
    id ??= caseIdOf(await api.createCase());
    if (id === null) return { state: 'unavailable' };
    await send(id);
  } catch (error) {
    const notice = refusalOf(error);
    if (id === null) return { state: 'unavailable' };
    return notice === null ? { state: 'unavailable', caseId: id } : reopenWith(api, id, notice);
  }
  const opened = await openCase(api, id);
  return opened.state === 'ready' ? opened : { state: 'unavailable', caseId: id };
}

/**
 * Upload one file into the open case (or a new one) and open it. A file over the backend's
 * limit is refused here, before the webview reads it.
 *
 * @param {CaseApi} api
 * @param {string | null} caseId
 * @param {PickedFile} file
 * @returns {Promise<CaseState>}
 */
export function addFile(api, caseId, file) {
  if ((file.size ?? 0) > MAX_FILE_BYTES) {
    return caseId === null
      ? Promise.resolve({ state: 'idle', notice: 'document_too_large' })
      : reopenWith(api, caseId, 'document_too_large');
  }
  return addDocument(api, caseId, async (id) => {
    const bytes = await file.arrayBuffer();
    const contentType = file.type || 'application/octet-stream';
    await api.uploadDocument(id, { filename: file.name, contentType, bytes });
  });
}

/**
 * Upload several files (the EOB and the denial letter dropped together) into one case, in
 * order; the first that does not end ready stops the rest.
 *
 * @param {CaseApi} api
 * @param {string | null} caseId
 * @param {PickedFile[]} files
 * @returns {Promise<CaseState>}
 */
export async function addFiles(api, caseId, files) {
  /** @type {CaseState} */
  let state = { state: 'idle' };
  let id = caseId;
  for (const file of files) {
    state = await addFile(api, id, file);
    if (state.state !== 'ready' || state.notice) return state;
    id = state.caseId;
  }
  return state;
}

/**
 * Create a case, upload one document into it, and open it.
 *
 * @param {CaseApi} api
 * @param {PickedFile} file
 * @returns {Promise<CaseState>}
 */
export function uploadCase(api, file) {
  return addFile(api, null, file);
}

/**
 * Attach pasted text (835 or a letter) to the open case (or a new one) and open it.
 *
 * @param {CaseApi} api
 * @param {string | null} caseId
 * @param {string} text
 * @returns {Promise<CaseState>}
 */
export function addText(api, caseId, text) {
  return addDocument(api, caseId, (id) => api.pasteText(id, text));
}

/**
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export async function openCase(api, caseId) {
  try {
    const body = await api.getCase(caseId);
    return caseIdOf(body) === caseId ? readyFrom(caseId, body) : { state: 'unavailable' };
  } catch {
    return { state: 'unavailable' };
  }
}

/**
 * A processing state: `diagnosing` for a diagnosis (US-6.1), `drafting` for a draft (US-7.1),
 * neither for an extraction (US-5.2).
 *
 * @param {string} caseId
 * @param {number} progress
 * @param {JobKind} kind
 * @returns {CaseState}
 */
function processing(caseId, progress, kind) {
  if (kind === 'diagnose') return { state: 'processing', caseId, progress, diagnosing: true };
  if (kind === 'draft') return { state: 'processing', caseId, progress, drafting: true };
  return { state: 'processing', caseId, progress };
}

/**
 * A job body's kind; anything unknown reads as an extraction, as before US-6.1.
 *
 * @param {unknown} body
 * @returns {JobKind}
 */
function kindOf(body) {
  const kind = /** @type {{ kind?: unknown } | null} */ (body)?.kind;
  return kind === 'diagnose' || kind === 'draft' ? kind : 'extract';
}

/**
 * Start a case job and report it as processing. The case runs one job at a time, so the job may
 * be one already running (its `kind` says which).
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {(caseId: string) => Promise<unknown>} start
 * @returns {Promise<CaseState>}
 */
async function startJob(api, caseId, start) {
  try {
    return processing(caseId, 0, kindOf(await start(caseId)));
  } catch (error) {
    const notice = refusalOf(error);
    return notice === null ? { state: 'unavailable' } : reopenWith(api, caseId, notice);
  }
}

/**
 * Start the pipeline for a case. Progress arrives as `plugin.claimcoach.case.progress` events.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export function processCase(api, caseId) {
  return startJob(api, caseId, api.processCase);
}

/**
 * Diagnose an extracted case (US-6.1). Progress arrives as `plugin.claimcoach.case.progress`.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export function diagnoseCase(api, caseId) {
  return startJob(api, caseId, api.diagnoseCase);
}

/**
 * Draft the diagnosed case's appeal letter (US-7.1). Progress arrives as
 * `plugin.claimcoach.case.progress`.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export function draftCase(api, caseId) {
  return startJob(api, caseId, api.draftCase);
}

/**
 * Store the editor's text as the case's draft, and show the case again (US-7.2).
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {string} text
 * @returns {Promise<CaseState>}
 */
export async function saveDraft(api, caseId, text) {
  try {
    const body = await api.saveDraft(caseId, text);
    return caseIdOf(body) === caseId ? readyFrom(caseId, body) : { state: 'unavailable' };
  } catch (error) {
    const code = codeOf(error);
    const notice = code === 'invalid_request' ? 'invalid_draft' : known(code);
    return notice === null ? { state: 'unavailable' } : reopenWith(api, caseId, notice);
  }
}

/**
 * Export the stored draft and hand the file to the host's save dialog (US-7.2 decision 4). The
 * save action is captured before the request, as the SDK asks; without one, the result says where
 * the file is and until when.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {ExportFormat} format
 * @param {(() => SaveFile) | undefined} capture `captureGatewayFileDownload`, when the host has it
 * @returns {Promise<ExportResult>}
 */
export async function exportDraft(api, caseId, format, capture) {
  const save = capture?.();
  let body;
  try {
    body = /** @type {{ case_id?: unknown, path?: unknown, filename?: unknown,
     *   expires_at?: unknown } | null} */ (await api.exportDraft(caseId, format));
  } catch (error) {
    const notice = known(codeOf(error));
    return notice === null ? { state: 'failed' } : { state: 'refused', notice };
  }
  const { path, filename, expires_at: expiresAt } = body ?? {};
  if (
    caseIdOf(body) !== caseId ||
    typeof path !== 'string' ||
    !path ||
    typeof filename !== 'string' ||
    !filename.endsWith(`.${format}`) ||
    typeof expiresAt !== 'string'
  ) {
    return { state: 'failed' };
  }
  if (save) {
    await save(path, filename); // never rejects: the host shows Saved or Download failed
    return { state: 'saved', format };
  }
  return { state: 'written', format, path, expiresAt };
}

/**
 * @param {ExportResult} result
 * @returns {string}
 */
export function describeExport(result) {
  switch (result.state) {
    case 'exporting':
      return `Exporting the ${result.format.toUpperCase()}…`;
    case 'saved':
      return `The ${result.format.toUpperCase()} went to the save dialog.`;
    case 'written':
      return (
        `The ${result.format.toUpperCase()} is on this Mac at ${result.path} until ` +
        `${result.expiresAt}; copy it from there before it is removed.`
      );
    case 'refused':
      return REFUSALS[result.notice];
    default:
      return 'The export did not finish; check that the worker is running and export again.';
  }
}

/**
 * After an extraction: show the case, and diagnose it when every field was read (US-6.1). A case
 * with fields to confirm waits for the biller, who confirms them and then presses Diagnose case.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {() => boolean} [follow] Called just before the diagnosis is requested, so the pane
 *   follows its events before any can arrive; `false` means a newer action replaced this one,
 *   and nothing is started.
 * @returns {Promise<CaseState>}
 */
export async function afterExtraction(api, caseId, follow = () => true) {
  const opened = await openCase(api, caseId);
  const read =
    opened.state === 'ready' &&
    opened.fields.length > 0 &&
    opened.fields.every((field) => field.status !== 'unreadable');
  return read && follow() ? diagnoseCase(api, caseId) : opened;
}

/**
 * Store the biller's value for one field as confirmed, and show the case again.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {string} path
 * @param {string} value
 * @returns {Promise<CaseState>}
 */
export async function confirmField(api, caseId, path, value) {
  try {
    const body = await api.confirmField(caseId, path, value);
    return caseIdOf(body) === caseId ? readyFrom(caseId, body) : { state: 'unavailable' };
  } catch (error) {
    const code = codeOf(error);
    const notice = code === 'invalid_request' ? 'invalid_value' : known(code);
    return notice === null ? { state: 'unavailable' } : reopenWith(api, caseId, notice);
  }
}

/**
 * Record how the case ended, which closes it, and show the case again (US-8.1). A refusal
 * because a job is running says to wait for it.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {Outcome} outcome
 * @returns {Promise<CaseState>}
 */
export async function recordOutcome(api, caseId, outcome) {
  try {
    const body = await api.recordOutcome(caseId, outcome);
    return caseIdOf(body) === caseId ? readyFrom(caseId, body) : { state: 'unavailable' };
  } catch (error) {
    const code = codeOf(error);
    const notice = code === 'model_busy' ? 'outcome_busy' : known(code);
    return notice === null ? { state: 'unavailable' } : reopenWith(api, caseId, notice);
  }
}

/**
 * @param {CaseState} current
 * @returns {string}
 */
export function describeCase(current) {
  switch (current.state) {
    case 'idle': {
      const notice = current.notice ? `${REFUSALS[current.notice]} ` : '';
      return `${notice}Drop a denial document (EOB, ERA, or payer letter) to start a case.`;
    }
    case 'busy':
      return 'Uploading…';
    case 'ready': {
      const notice = current.notice ? `${REFUSALS[current.notice]} ` : '';
      const pending = current.fields?.filter((f) => f.status === 'unreadable').length ?? 0;
      const others = current.otherClaims
        ? ` This 835 holds ${current.otherClaims} more claim(s); start a case for each.`
        : '';
      const unread = current.unreadSources
        ? ` ${current.unreadSources} document(s) could not be read; enter their fields by hand.`
        : '';
      const next = pending
        ? `: ${pending} field(s) need confirmation; confirm them, then diagnose the case.`
        : current.fields?.length
          ? ': every field is read or confirmed.'
          : ' is ready to process.';
      const stale = current.diagnosis?.stale
        ? ' The fields changed since the diagnosis; diagnose the case again.'
        : '';
      const closed = current.closed
        ? ' This case is closed; start a new case for more documents.'
        : '';
      return `${notice}Case ${current.caseId}${next}${unread}${others}${stale}${closed}`;
    }
    case 'processing': {
      const verb = current.drafting
        ? 'Drafting the appeal for'
        : current.diagnosing
          ? 'Diagnosing'
          : 'Processing';
      return `${verb} case ${current.caseId} on this Mac… ${Math.round((current.progress ?? 0) * 100)}%`;
    }
    default:
      return 'Case work is not available. Check that the ClaimCoach backend and worker are running.';
  }
}

/**
 * Ask the backend half for worker health. Any failure (backend half disabled, worker stopped,
 * error envelope) reads as `unavailable`; the envelope text is never shown (BR-14).
 *
 * @param {RestFn} rest
 * @returns {Promise<WorkerState>}
 */
export async function loadWorkerState(rest) {
  try {
    const body = /** @type {Partial<HealthResponse> | null} */ (await rest('/health'));
    if (body?.ok === true && typeof body.version === 'string') {
      return { state: 'ok', version: body.version };
    }
  } catch {
    // ctx.rest rejects on non-2xx and when the Python half is not enabled.
  }
  return { state: 'unavailable' };
}

/**
 * @param {WorkerState} worker
 * @returns {string}
 */
export function describeWorker(worker) {
  if (worker.state === 'ok') return `Worker running (v${worker.version})`;
  if (worker.state === 'loading') return 'Checking worker…';
  return 'Worker not running. Enable the ClaimCoach backend and start the worker.';
}

/**
 * @param {{ rest: RestFn }} props
 */
export function WorkerStatus({ rest }) {
  const [worker, setWorker] = useState(/** @type {WorkerState} */ ({ state: 'loading' }));
  useEffect(() => {
    let current = true;
    loadWorkerState(rest).then((next) => {
      if (current) setWorker(next);
    });
    return () => {
      current = false;
    };
  }, [rest]);
  return jsx('p', { role: 'status', children: describeWorker(worker) });
}

/**
 * @param {DocumentView[]} documents
 */
export function DocumentList(documents) {
  return jsx('ul', {
    'aria-label': 'Source documents',
    children: documents.map((doc) =>
      jsx('li', { 'data-kind': doc.kind, children: doc.label }, doc.docId),
    ),
  });
}

/**
 * The extracted fields; an unreadable one is highlighted and waits for the biller's value.
 *
 * @param {{ fields: FieldView[], edits: Record<string, string>,
 *   onEdit: (path: string, value: string) => void, onConfirm: (path: string) => void,
 *   disabled: boolean }} props
 */
export function FieldList({ fields, edits, onEdit, onConfirm, disabled }) {
  return jsx('ul', {
    'aria-label': 'Extracted fields',
    children: fields.map((field) => {
      const unreadable = field.status === 'unreadable';
      const value = edits[field.path] ?? field.value;
      return jsxs(
        'li',
        {
          'data-status': field.status,
          'aria-invalid': unreadable,
          style: unreadable ? { outline: '2px solid #d97706', background: '#fef3c7' } : undefined,
          children: [
            jsx('label', {
              children: unreadable ? `${field.label} (needs confirmation)` : field.label,
            }),
            jsx('input', {
              'aria-label': field.label,
              value,
              disabled,
              /** @param {{ currentTarget: { value: string } }} event */
              onChange: (event) => onEdit(field.path, event.currentTarget.value),
            }),
            jsx('button', {
              type: 'button',
              disabled: disabled || !value.trim(),
              onClick: () => onConfirm(field.path),
              children: field.status === 'confirmed' ? 'Confirmed' : 'Confirm',
            }),
          ],
        },
        field.path,
      );
    }),
  });
}

/**
 * The missing-documentation checklist and the rule cards it came from (US-6.2). Without a rule
 * card for the payer there is no checklist, and the pane says why: an unreadable payer, which the
 * biller confirms, or no card on file, which the manager adds.
 *
 * @param {DiagnosisView} diagnosis
 * @param {string} [today] `YYYY-MM-DD`; this Mac's date by default
 */
export function ChecklistPanel(diagnosis, today = isoToday()) {
  if (diagnosis.cards.length === 0) {
    return jsx('p', {
      role: 'note',
      children: diagnosis.payerRead
        ? "No rule card is on file for this payer, so there is no checklist. Add the payer's " +
          'rule cards to the global corpus.'
        : 'The payer could not be read, so no rule card was matched: confirm the payer, then ' +
          'diagnose the case again.',
    });
  }
  return jsxs('section', {
    'aria-label': 'Missing documentation',
    children: [
      jsx('h4', { children: 'Missing documentation' }),
      diagnosis.checklist.length
        ? jsx('ul', {
            'aria-label': 'Checklist',
            children: diagnosis.checklist.map((item, i) =>
              jsx(
                'li',
                { children: item.why ? `${item.document}: ${item.why}` : item.document },
                `c${i}`,
              ),
            ),
          })
        : jsx('p', { children: "The payer's rule cards list no required documents." }),
      jsx('ul', {
        'aria-label': 'Rule cards',
        children: diagnosis.cards.map((card) => {
          const stale = card.stale || staleOn(card.verifiedOn, today);
          return jsx(
            'li',
            {
              'data-stale': stale,
              children:
                `${card.key}: ${card.source}, verified ${card.verifiedOn}` +
                (stale ? ' (stale: check that it is still current)' : ''),
            },
            card.key,
          );
        }),
      }),
    ],
  });
}

/**
 * The appeal deadline, flagged once it has passed, or why it is unknown (US-6.3).
 *
 * @param {DeadlineView | undefined} deadline
 * @param {string} today `YYYY-MM-DD`
 */
export function DeadlineLine(deadline, today) {
  if (!deadline) return null;
  const { text, passed } = describeDeadline(deadline, today);
  return jsx('p', {
    'aria-label': 'Appeal deadline',
    'data-status': deadline.status,
    'data-passed': passed,
    style: passed ? { color: '#b91c1c', fontWeight: 600 } : undefined,
    children: text,
  });
}

/**
 * The diagnosis: the denial reason, then the appeal likelihood with every reason (US-6.1), then
 * the explanation, the likely root cause, and the checklist once the explanation ran (US-6.2).
 *
 * @param {DiagnosisView | undefined} diagnosis
 * @param {string} [today] `YYYY-MM-DD`; this Mac's date by default
 */
export function DiagnosisPanel(diagnosis, today = isoToday()) {
  if (!diagnosis) return null;
  const likelihood = `${diagnosis.likelihood[0]?.toUpperCase()}${diagnosis.likelihood.slice(1)}`;
  return jsxs('section', {
    'aria-label': 'Diagnosis',
    'data-stale': diagnosis.stale,
    children: [
      jsx('h3', { children: `Denial reason: ${DENIAL_REASONS[diagnosis.reason]}` }),
      jsx('p', { children: `Codes: ${diagnosis.codes.join(', ') || 'none read'}` }),
      jsx('h4', { children: `Appeal likelihood: ${likelihood}` }),
      jsx('ul', {
        'aria-label': 'Why',
        children: diagnosis.reasons.map((reason, i) => jsx('li', { children: reason }, `r${i}`)),
      }),
      diagnosis.stale
        ? jsx('p', { role: 'note', children: 'Out of date: the fields changed since it ran.' })
        : null,
      diagnosis.explanation
        ? jsxs('div', {
            'aria-label': 'Explanation',
            children: [
              jsx('p', { children: diagnosis.explanation.text }),
              jsx('p', { children: `Likely root cause: ${diagnosis.explanation.rootCause}` }),
            ],
          })
        : null,
      diagnosis.explanation ? ChecklistPanel(diagnosis, today) : null,
    ],
  });
}

/**
 * The appeal draft under its review label, in an editor, with Save draft and the exports (US-7.1,
 * US-7.2). Export is offered only for saved text, because the stored draft is what is exported.
 *
 * A closed case (US-8.1) still exports, but its draft can no longer be edited.
 *
 * @param {{ draft: DraftView | undefined, letter: string | null, result: ExportResult | null,
 *   disabled: boolean, closed?: boolean, onLetter: (text: string) => void, onSave: () => void,
 *   onExport: (format: ExportFormat) => void }} props
 */
export function DraftPanel({
  draft,
  letter,
  result,
  disabled,
  closed = false,
  onLetter,
  onSave,
  onExport,
}) {
  if (!draft) return null;
  const text = letter ?? draft.text;
  const dirty = text !== draft.text;
  // One export at a time: a double-click would write two files and open two save dialogs.
  const exporting = result?.state === 'exporting';
  const cards = draft.ruleCards.length
    ? ` with the rule cards ${draft.ruleCards.join(', ')}.`
    : '. No rule card was on file for this payer: check its appeal rules yourself.';
  return jsxs('section', {
    'aria-label': 'Appeal draft',
    'data-stale': draft.stale,
    children: [
      jsx('h3', { children: 'Draft for human review' }),
      jsx('p', { children: `Drafted from the template ${draft.templateId}${cards}` }),
      draft.stale
        ? jsx('p', {
            role: 'note',
            children: 'The case changed since this draft was made; check it, or draft again.',
          })
        : null,
      jsx('textarea', {
        'aria-label': 'Appeal letter (draft for human review)',
        value: text,
        maxLength: MAX_LETTER_CHARS,
        disabled: disabled || closed,
        /** @param {{ currentTarget: { value: string } }} event */
        onChange: (event) => onLetter(event.currentTarget.value),
      }),
      jsx('button', {
        type: 'button',
        disabled: disabled || closed || !dirty || !text.trim(),
        onClick: onSave,
        children: 'Save draft',
      }),
      jsx('button', {
        type: 'button',
        disabled: disabled || dirty || exporting,
        onClick: () => onExport('pdf'),
        children: 'Export PDF',
      }),
      jsx('button', {
        type: 'button',
        disabled: disabled || dirty || exporting,
        onClick: () => onExport('docx'),
        children: 'Export DOCX',
      }),
      dirty ? jsx('p', { role: 'note', children: 'Save the draft before exporting it.' }) : null,
      result
        ? jsx('p', { role: 'status', 'aria-label': 'Export', children: describeExport(result) })
        : null,
    ],
  });
}

/**
 * How the case ended, with a Mark button per outcome (US-8.1). Marking closes the case, which
 * cannot be undone, so on an open case Mark asks first (`pending`) and the outcome is recorded on
 * Close the case; on a closed case Mark corrects the outcome at once.
 *
 * @param {{ outcome: OutcomeView | undefined, closed: boolean, disabled: boolean,
 *   pending?: Outcome | null, onMark: (outcome: Outcome) => void,
 *   onConfirm?: () => void, onCancel?: () => void }} props
 */
export function OutcomePanel({
  outcome,
  closed,
  disabled,
  pending = null,
  onMark,
  onConfirm = noop,
  onCancel = noop,
}) {
  const recorded = outcome
    ? `Outcome: ${OUTCOMES[outcome.outcome]} (recorded ${outcome.recordedAt.slice(0, 10)}).`
    : 'No outcome recorded yet. Marking one closes the case.';
  const asking = pending !== null && !closed && !disabled;
  return jsxs('section', {
    'aria-label': 'Case outcome',
    children: [
      jsx('h3', { children: 'Outcome' }),
      jsx('p', { role: 'status', children: recorded }),
      closed ? jsx('p', { children: 'Case closed.' }) : null,
      ...Object.entries(OUTCOMES).map(([value, label]) =>
        jsx('button', {
          type: 'button',
          disabled: disabled || asking || outcome?.outcome === value,
          onClick: () => onMark(/** @type {Outcome} */ (value)),
          children: `Mark ${label.toLowerCase()}`,
        }),
      ),
      asking
        ? jsxs('div', {
            role: 'alertdialog',
            'aria-label': 'Close the case',
            children: [
              jsx('p', {
                children:
                  `Mark the case ${OUTCOMES[pending].toLowerCase()}? This closes the case: it ` +
                  'takes no more documents, fields, or edits, and cannot be reopened.',
              }),
              jsx('button', { type: 'button', onClick: onConfirm, children: 'Close the case' }),
              jsx('button', { type: 'button', onClick: onCancel, children: 'Cancel' }),
            ],
          })
        : null,
    ],
  });
}

/** What a job of each kind ends with when its event names no known code. */
const JOB_FAILED = Object.freeze({
  extract: 'extraction_failed',
  diagnose: 'diagnosis_failed',
  draft: 'drafting_failed',
});

/**
 * The kind of job a processing state follows.
 *
 * @param {Extract<CaseState, { state: 'processing' }>} state
 * @returns {JobKind}
 */
function kindOfState(state) {
  return state.drafting ? 'draft' : state.diagnosing ? 'diagnose' : 'extract';
}

/**
 * The Draft appeal button's text: drafting again replaces the draft, edits included (US-7.1
 * decision 7).
 *
 * @param {DraftView | undefined} draft
 */
export function draftButtonLabel(draft) {
  if (!draft) return 'Draft appeal';
  return draft.edited ? 'Draft again (replaces your edits)' : 'Draft again';
}

/**
 * Whether the editor holds text the biller has not saved (US-7.2).
 *
 * @param {DraftView | undefined} draft
 * @param {string | null} letter
 */
function unsaved(draft, letter) {
  return draft !== undefined && letter !== null && letter !== draft.text;
}

/** Does nothing: the disposer of no subscription, and the pane's handler before its first render. */
function noop() {}

/** @type {SubscribeFn} */
const noEvents = () => noop;

/**
 * The case pane. The whole pane is the drop zone; the file input, the paste box, and a drop all
 * add to the open case, or start one. Processing progress arrives through `subscribe`.
 *
 * @param {{ rest: RestFn, subscribe?: SubscribeFn }} props
 */
export function CasePane({ rest, subscribe = noEvents }) {
  const api = createCaseApi(rest);
  const [current, setCurrent] = useState(/** @type {CaseState} */ ({ state: 'idle' }));
  // One object per mounted pane: answers that arrive after unmount, or after a newer action
  // started, are dropped (the last action wins, never the slowest one). It also carries the case
  // being processed and this render's event handler to the long-lived event subscription.
  const [life] = useState(
    /** @type {{ live: boolean, action: number, caseId: string | null,
     *   processing: string | null, kind?: JobKind,
     *   onProgress: (payload: unknown) => void }} */ ({
      live: true,
      action: 0,
      caseId: null,
      processing: null,
      onProgress: noop,
    }),
  );
  const [draft, setDraft] = useState('');
  const [edits, setEdits] = useState(/** @type {Record<string, string>} */ ({}));
  // The appeal editor's unsaved text (null: the stored draft as it is) and the last export.
  const [letter, setLetter] = useState(/** @type {string | null} */ (null));
  const [exported, setExported] = useState(/** @type {ExportResult | null} */ (null));
  // The outcome the biller chose for an open case, until they confirm that it closes the case.
  const [pendingOutcome, setPendingOutcome] = useState(/** @type {Outcome | null} */ (null));
  // A closed case (US-8.1) takes no documents, fields, jobs, or edits; it still exports.
  const closed = current.state === 'ready' && current.closed === true;
  useEffect(() => {
    life.live = true;
    return () => {
      life.live = false;
    };
  }, [life]);
  useEffect(() => subscribe((payload) => life.onProgress(payload)), [subscribe, life]);
  /** @param {Promise<CaseState>} pending */
  const settle = (pending) => {
    life.action += 1;
    const action = life.action;
    setCurrent({ state: 'busy' });
    setExported(null);
    setPendingOutcome(null);
    pending.then((next) => {
      if (!life.live || action !== life.action) return;
      // The last case this pane worked on stays open across failures, so the next document
      // joins it instead of starting a second case. Values typed for another case are dropped.
      if ('caseId' in next && next.caseId) {
        if (next.caseId !== life.caseId) {
          setEdits({});
          setLetter(null);
        }
        life.caseId = next.caseId;
      }
      // The job that runs may be another kind than the one asked for (one job per case); an
      // answer that is not a running job leaves no job followed, so a refused start does not
      // read a later job's events as its own.
      if (next.state === 'processing') follow(next.caseId, kindOfState(next));
      else follow(null, 'extract');
      setCurrent(next);
    });
  };
  /**
   * Follow a job's events from now on: called before its start request is sent, so an event that
   * arrives before the answer is not missed.
   *
   * @param {string | null} caseId
   * @param {JobKind} kind
   */
  const follow = (caseId, kind) => {
    life.processing = caseId;
    life.kind = kind;
  };
  life.onProgress = (payload) => {
    const progress = progressOf(payload);
    const caseId = life.processing;
    if (!life.live || progress === null || caseId === null || progress.caseId !== caseId) return;
    const kind = life.kind ?? 'extract';
    if (progress.stage === 'done' || progress.stage === 'failed') {
      follow(null, 'extract');
      setEdits({}); // fresh values replace anything typed before the run
      if (kind === 'draft' && progress.stage === 'done') setLetter(null); // the new draft shows
      const notice = known(progress.errorCode) ?? JOB_FAILED[kind];
      const chained = life.action + 1; // the action settle starts next
      settle(
        progress.stage === 'failed'
          ? reopenWith(api, caseId, notice)
          : kind !== 'extract'
            ? openCase(api, caseId)
            : afterExtraction(api, caseId, () => {
                if (!life.live || life.action !== chained) return false;
                follow(caseId, 'diagnose');
                return true;
              }),
      );
    } else {
      setCurrent(processing(caseId, progress.progress, kind));
    }
  };
  /** @param {ArrayLike<PickedFile> | null | undefined} files */
  const addPicked = (files) => {
    const picked = Array.from(files ?? []);
    if (picked.length === 0 || current.state === 'busy' || closed) return;
    settle(addFiles(api, life.caseId, picked));
  };
  /** @param {{ currentTarget: { files: ArrayLike<PickedFile> | null } }} event */
  const onFile = (event) => addPicked(event.currentTarget.files);
  /** @param {{ preventDefault: () => void, dataTransfer: { files: ArrayLike<PickedFile> } | null }} event */
  const onDrop = (event) => {
    event.preventDefault(); // keep the webview from opening the file
    addPicked(event.dataTransfer?.files);
  };
  /** @param {{ preventDefault: () => void }} event */
  const onDragOver = (event) => event.preventDefault(); // marks the pane as a drop target
  const onProcess = () => {
    if (current.state !== 'ready') return;
    follow(current.caseId, 'extract');
    settle(processCase(api, current.caseId));
  };
  const onDiagnose = () => {
    if (current.state !== 'ready') return;
    follow(current.caseId, 'diagnose');
    settle(diagnoseCase(api, current.caseId));
  };
  const onDraftAppeal = () => {
    if (current.state !== 'ready') return;
    follow(current.caseId, 'draft');
    settle(draftCase(api, current.caseId));
  };
  const onSaveDraft = () => {
    if (current.state !== 'ready' || letter === null || !letter.trim()) return;
    const text = letter;
    settle(
      saveDraft(api, current.caseId, text).then((next) => {
        // A save that was refused keeps the text in the editor, so it need not be typed again.
        if (life.live && next.state === 'ready' && !next.notice) setLetter(null);
        return next;
      }),
    );
  };
  /** @param {ExportFormat} format */
  const onExport = (format) => {
    if (current.state !== 'ready' || !current.draft || exported?.state === 'exporting') return;
    const caseId = current.caseId;
    setExported({ state: 'exporting', format });
    exportDraft(api, caseId, format, sdk.captureGatewayFileDownload).then((result) => {
      if (life.live && life.caseId === caseId) setExported(result);
    });
  };
  /** @param {Outcome} outcome */
  const onOutcome = (outcome) => {
    if (current.state !== 'ready') return;
    // Closing cannot be undone, so an open case asks first; a closed one is only corrected.
    if (current.closed) settle(recordOutcome(api, current.caseId, outcome));
    else setPendingOutcome(outcome);
  };
  const onConfirmOutcome = () => {
    if (current.state !== 'ready' || pendingOutcome === null) return;
    setPendingOutcome(null);
    settle(recordOutcome(api, current.caseId, pendingOutcome));
  };
  const onCancelOutcome = () => setPendingOutcome(null);
  const onRefresh = () => {
    if (life.caseId === null || current.state === 'busy') return;
    follow(null, 'extract');
    setEdits({});
    settle(openCase(api, life.caseId));
  };
  const onNewCase = () => {
    life.action += 1; // an upload still running no longer updates the pane
    life.caseId = null;
    follow(null, 'extract');
    setEdits({});
    setLetter(null);
    setExported(null);
    setPendingOutcome(null);
    setCurrent({ state: 'idle' });
  };
  /** @param {{ currentTarget: { value: string } }} event */
  const onDraft = (event) => setDraft(event.currentTarget.value);
  const onPaste = () => {
    const text = draft;
    if (!text.trim() || current.state === 'busy' || closed) return;
    setDraft('');
    settle(
      addText(api, life.caseId, text).then((next) => {
        // A paste that was not attached goes back into the box, so it need not be found again.
        if (life.live && (next.state !== 'ready' || next.notice)) setDraft(text);
        return next;
      }),
    );
  };
  /**
   * @param {string} path
   * @param {string} value
   */
  const onEdit = (path, value) => setEdits({ ...edits, [path]: value });
  /** @param {string} path */
  const onConfirm = (path) => {
    if (current.state !== 'ready') return;
    const field = current.fields.find((f) => f.path === path);
    const value = field ? (edits[path] ?? field.value).trim() : '';
    if (!value) return;
    const { [path]: _done, ...rest } = edits;
    setEdits(rest);
    settle(confirmField(api, current.caseId, path, value));
  };
  return jsxs('section', {
    'aria-label': 'ClaimCoach cases',
    onDragOver,
    onDrop,
    children: [
      jsx('h2', { children: 'ClaimCoach' }),
      jsx(WorkerStatus, { rest }),
      jsx('input', {
        type: 'file',
        'aria-label': 'Upload a denial document',
        accept: '.pdf,.png,.jpg,.jpeg,.txt,.835',
        disabled: current.state === 'busy' || closed,
        onChange: onFile,
      }),
      jsx('p', { role: 'status', children: describeCase(current) }),
      jsx('button', {
        type: 'button',
        disabled: current.state !== 'ready' || closed,
        onClick: onProcess,
        children: 'Process case',
      }),
      jsx('button', {
        type: 'button',
        disabled: current.state === 'idle' || current.state === 'busy',
        onClick: onNewCase,
        children: 'New case',
      }),
      jsx('textarea', {
        'aria-label': 'Paste 835 or letter text',
        value: draft,
        disabled: current.state === 'busy' || closed,
        onChange: onDraft,
      }),
      jsx('button', {
        type: 'button',
        disabled: current.state === 'busy' || closed || !draft.trim(),
        onClick: onPaste,
        children: 'Attach pasted text',
      }),
      DocumentList(current.state === 'ready' ? current.documents : []),
      jsx('button', {
        type: 'button',
        disabled: life.caseId === null || current.state === 'busy',
        onClick: onRefresh,
        children: 'Refresh case',
      }),
      jsx(FieldList, {
        fields: current.state === 'ready' ? current.fields : [],
        edits,
        onEdit,
        onConfirm,
        disabled: current.state !== 'ready' || closed,
      }),
      jsx('button', {
        type: 'button',
        disabled: current.state !== 'ready' || closed || !current.fields?.length,
        onClick: onDiagnose,
        children: 'Diagnose case',
      }),
      DeadlineLine(current.state === 'ready' ? current.deadline : undefined, isoToday()),
      DiagnosisPanel(current.state === 'ready' ? current.diagnosis : undefined),
      jsx('button', {
        type: 'button',
        // Unsaved editor text would be lost to the new draft: save it first (US-7.2).
        disabled:
          current.state !== 'ready' ||
          closed ||
          !current.diagnosis ||
          current.diagnosis.stale === true ||
          unsaved(current.draft, letter),
        onClick: onDraftAppeal,
        children: draftButtonLabel(current.state === 'ready' ? current.draft : undefined),
      }),
      jsx(DraftPanel, {
        draft: current.state === 'ready' ? current.draft : undefined,
        letter,
        result: exported,
        disabled: current.state !== 'ready',
        closed,
        onLetter: setLetter,
        onSave: onSaveDraft,
        onExport,
      }),
      jsx(OutcomePanel, {
        outcome: current.state === 'ready' ? current.outcome : undefined,
        closed,
        // A closed case takes no edits, so unsaved editor text is saved first.
        disabled: current.state !== 'ready' || unsaved(current.draft, letter),
        pending: pendingOutcome,
        onMark: onOutcome,
        onConfirm: onConfirmOutcome,
        onCancel: onCancelOutcome,
      }),
    ],
  });
}

/**
 * @param {unknown} value
 * @returns {value is number}
 */
const isCount = (value) => Number.isInteger(value) && /** @type {number} */ (value) >= 0;

/**
 * Outcome counts, when well-formed (US-8.2).
 *
 * @param {unknown} value
 * @returns {CountsView | null}
 */
function countsOf(value) {
  const counts = /** @type {{ overturned?: unknown, upheld?: unknown, written_off?: unknown,
   *   total?: unknown, overturn_rate?: unknown } | null | undefined} */ (value);
  const { overturned, upheld, written_off: writtenOff, total } = counts ?? {};
  if (!isCount(overturned) || !isCount(upheld) || !isCount(writtenOff) || !isCount(total)) {
    return null;
  }
  const rate = typeof counts?.overturn_rate === 'number' ? counts.overturn_rate : null;
  return { overturned, upheld, writtenOff, total, rate };
}

/**
 * The weekly summary's body, when well-formed (US-8.2); malformed rows are left out.
 *
 * @param {unknown} body
 * @returns {SummaryView | null}
 */
export function summaryOf(body) {
  const summary = /** @type {{ week?: unknown, timezone?: unknown, profiles?: unknown,
   *   not_shared?: unknown, unreadable?: unknown, totals?: unknown, by_category?: unknown,
   *   by_code?: unknown } | null} */ (body);
  const totals = countsOf(summary?.totals);
  if (
    typeof summary?.week !== 'string' ||
    typeof summary.timezone !== 'string' ||
    !isCount(summary.not_shared) ||
    totals === null
  ) {
    return null;
  }
  const rows = Array.isArray(summary.by_category) ? summary.by_category : [];
  const categories = rows.flatMap((entry) => {
    const row = /** @type {{ payer?: unknown, denial_reason?: unknown } | null} */ (entry);
    const counts = countsOf(row);
    const reason = row?.denial_reason;
    const listed = typeof reason === 'string' && Object.hasOwn(DENIAL_REASONS, reason);
    if (counts === null || (reason !== null && !listed)) return [];
    const payer = typeof row?.payer === 'string' ? row.payer : null;
    return [{ ...counts, payer, reason: listed ? /** @type {DenialReason} */ (reason) : null }];
  });
  const codeRows = Array.isArray(summary.by_code) ? summary.by_code : [];
  const codes = codeRows.flatMap((entry) => {
    const row = /** @type {{ payer?: unknown, code?: unknown } | null} */ (entry);
    const counts = countsOf(row);
    if (counts === null || typeof row?.code !== 'string') return [];
    const payer = typeof row.payer === 'string' ? row.payer : null;
    return [{ ...counts, payer, code: row.code }];
  });
  return {
    week: summary.week,
    timezone: summary.timezone,
    profiles: stringsOf(summary.profiles),
    notShared: summary.not_shared,
    unreadable: stringsOf(summary.unreadable).length,
    totals,
    categories,
    codes,
  };
}

/**
 * Read the last completed week's summary; any failure reads as unavailable.
 *
 * @param {RestFn} rest
 * @returns {Promise<SummaryState>}
 */
export async function loadSummary(rest) {
  try {
    const summary = summaryOf(await rest('/outcomes/summary'));
    return summary === null ? { state: 'unavailable' } : { state: 'ok', summary };
  } catch {
    return { state: 'unavailable' };
  }
}

/**
 * Counts as one line: `3 outcomes: 2 overturned, 1 upheld, 0 written off (67% overturned).`
 *
 * @param {CountsView} counts
 */
export function describeCounts(counts) {
  const rate = counts.rate === null ? '' : ` (${Math.round(counts.rate * 100)}% overturned)`;
  return (
    `${counts.total} outcome(s): ${counts.overturned} overturned, ${counts.upheld} upheld, ` +
    `${counts.writtenOff} written off${rate}.`
  );
}

/**
 * Which profiles the summary read, and which it did not.
 *
 * @param {SummaryView} summary
 */
export function describeSharing(summary) {
  const read = summary.profiles.length
    ? `Profiles sharing their outcomes: ${summary.profiles.join(', ')}.`
    : 'No profile shares its outcomes yet (Settings → Plugins → ClaimCoach).';
  const others = summary.notShared ? ` ${summary.notShared} profile(s) do not share theirs.` : '';
  const failed = summary.unreadable
    ? ` ${summary.unreadable} profile(s) could not be read this time.`
    : '';
  return `${read}${others}${failed}`;
}

/**
 * Ask for the fine-tune export with the manager's approval (US-8.3). A refusal or a malformed
 * answer never reads as written.
 *
 * @param {RestFn} rest
 * @param {string} manager
 * @returns {Promise<FineTuneResult>}
 */
export async function exportFineTune(rest, manager) {
  try {
    const body = /** @type {{ ok?: unknown, path?: unknown, records?: unknown } | null} */ (
      await rest('/outcomes/export', {
        method: 'POST',
        body: { approval: { manager, approved: true } },
      })
    );
    if (body?.ok !== true || typeof body.path !== 'string' || !isCount(body.records)) {
      return { state: 'failed' };
    }
    return { state: 'written', path: body.path, records: body.records };
  } catch (error) {
    const code = codeOf(error);
    return code === 'export_not_approved' || code === 'invalid_request'
      ? { state: 'refused' }
      : { state: 'failed' };
  }
}

/**
 * @param {FineTuneResult} result
 */
export function describeFineTune(result) {
  switch (result.state) {
    case 'exporting':
      return 'Exporting…';
    case 'written':
      return `${result.records} de-identified pair(s) written to ${result.path}.`;
    case 'refused':
      return 'The export needs your name and your approval; nothing was exported.';
    default:
      return 'The export could not be written; check that the ClaimCoach worker is running.';
  }
}

/**
 * The fine-tune export (US-8.3): explicit, approved by a named manager, never automatic.
 *
 * @param {{ manager: string, approved: boolean, result: FineTuneResult | null,
 *   onManager: (name: string) => void, onApproved: (approved: boolean) => void,
 *   onExport: () => void }} props
 */
export function FineTunePanel({ manager, approved, result, onManager, onApproved, onExport }) {
  const exporting = result?.state === 'exporting';
  return jsxs('section', {
    'aria-label': 'Fine-tune export',
    children: [
      jsx('h2', { children: 'Fine-tune export' }),
      jsx('p', {
        children:
          'Writes the de-identified case/outcome pairs of the profiles that share their outcomes ' +
          'to a file on this Mac. Nothing is exported without your approval.',
      }),
      jsx('input', {
        type: 'text',
        'aria-label': 'Approving manager',
        value: manager,
        maxLength: 80,
        disabled: exporting,
        /** @param {{ currentTarget: { value: string } }} event */
        onChange: (event) => onManager(event.currentTarget.value),
      }),
      jsx('input', {
        type: 'checkbox',
        'aria-label': 'I approve this de-identified export',
        checked: approved,
        disabled: exporting,
        /** @param {{ currentTarget: { checked: boolean } }} event */
        onChange: (event) => onApproved(event.currentTarget.checked),
      }),
      jsx('button', {
        type: 'button',
        disabled: exporting || !approved || !manager.trim(),
        onClick: onExport,
        children: 'Export fine-tune set',
      }),
      result ? jsx('p', { role: 'status', children: describeFineTune(result) }) : null,
    ],
  });
}

/**
 * The manager dashboard (US-8.2): the last completed week's denial patterns per payer and denial
 * reason, from de-identified outcomes of the profiles that share them, and the fine-tune export
 * (US-8.3). No case is shown.
 *
 * @param {{ rest: RestFn }} props
 */
export function DashboardPage({ rest }) {
  const [loaded, setLoaded] = useState(/** @type {SummaryState} */ ({ state: 'loading' }));
  const [manager, setManager] = useState('');
  const [approved, setApproved] = useState(false);
  const [fineTune, setFineTune] = useState(/** @type {FineTuneResult | null} */ (null));
  const [life] = useState({ live: true });
  useEffect(() => {
    let current = true;
    life.live = true;
    loadSummary(rest).then((next) => {
      if (current) setLoaded(next);
    });
    return () => {
      current = false;
      life.live = false;
    };
  }, [rest, life]);
  const onExport = () => {
    const name = manager.trim();
    if (!approved || !name || fineTune?.state === 'exporting') return;
    setFineTune({ state: 'exporting' });
    exportFineTune(rest, name).then((result) => {
      if (life.live) setFineTune(result);
    });
    setApproved(false); // each export is approved on its own
  };
  const heading = jsx('h1', { children: 'ClaimCoach dashboard' });
  if (loaded.state !== 'ok') {
    const text =
      loaded.state === 'loading'
        ? 'Loading the weekly outcome summary…'
        : 'The weekly outcome summary is unavailable; check that the ClaimCoach worker is running.';
    return jsxs('section', {
      'aria-label': 'ClaimCoach manager dashboard',
      children: [heading, jsx('p', { role: 'status', children: text })],
    });
  }
  const { summary } = loaded;
  return jsxs('section', {
    'aria-label': 'ClaimCoach manager dashboard',
    children: [
      heading,
      jsx('h2', { children: `Week ${summary.week} (${summary.timezone})` }),
      jsx('p', { role: 'status', children: describeSharing(summary) }),
      jsx('p', { children: `All payers: ${describeCounts(summary.totals)}` }),
      jsx('ul', {
        'aria-label': 'Outcomes per payer and denial reason',
        children: summary.categories.map((row) =>
          jsx(
            'li',
            {
              children:
                `${row.payer ?? 'Payer without rule cards'} · ` +
                `${row.reason ? DENIAL_REASONS[row.reason] : 'Not diagnosed'}: ` +
                describeCounts(row),
            },
            `${row.payer}/${row.reason}`,
          ),
        ),
      }),
      jsx('ul', {
        'aria-label': 'Outcomes per payer and code',
        children: summary.codes.map((row) =>
          jsx(
            'li',
            {
              children: `${row.payer ?? 'Payer without rule cards'} · ${row.code}: ${describeCounts(row)}`,
            },
            `${row.payer}/${row.code}`,
          ),
        ),
      }),
      jsx(FineTunePanel, {
        manager,
        approved,
        result: fineTune,
        onManager: setManager,
        onApproved: setApproved,
        onExport,
      }),
    ],
  });
}

/**
 * Read the richer-agent-access setting. Anything but an explicit `true` reads as off.
 *
 * @param {RestFn} rest
 * @returns {Promise<boolean>}
 */
export async function loadRicherAccess(rest) {
  try {
    const body = /** @type {{ ok?: unknown, richer_agent_access?: unknown } | null} */ (
      await rest('/settings')
    );
    return body?.ok === true && body.richer_agent_access === true;
  } catch {
    return false;
  }
}

/**
 * @param {{ rest: RestFn }} props
 */
export function LocalOnlyIndicator({ rest }) {
  const [richer, setRicher] = useState(false);
  useEffect(() => {
    let current = true;
    const refresh = () => {
      loadRicherAccess(rest).then((next) => {
        if (current) setRicher(next);
      });
    };
    refresh();
    // The setting is changed in Settings → Plugins while the statusbar stays mounted.
    const timer = setInterval(refresh, SETTINGS_REFRESH_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [rest]);
  const base = 'ClaimCoach runs on local models only. Case content never leaves this Mac.';
  return jsx('span', {
    title: richer
      ? `${base} Richer agent access is on; agent tool results are still redacted.`
      : base,
    children: richer ? 'Local-only · richer agent access on' : 'Local-only',
  });
}

/**
 * @param {{ rest: RestFn }} props
 */
export function SettingsPage({ rest }) {
  return jsxs('section', {
    'aria-label': 'ClaimCoach settings',
    children: [jsx('h2', { children: 'ClaimCoach' }), jsx(WorkerStatus, { rest })],
  });
}

/** @type {import('@hermes/plugin-sdk').HermesPlugin} */
const plugin = {
  id: PLUGIN_ID,
  name: 'ClaimCoach',
  description: 'Denial-management coach for medical billers. Local models only.',
  defaultEnabled: false,
  register(ctx) {
    /** @type {RestFn} */
    const rest = (path, opts) => (opts === undefined ? ctx.rest(path) : ctx.rest(path, opts));
    // Feature-detected (PC-3): without ctx.onEvent the biller presses Refresh case instead.
    /** @type {SubscribeFn} */
    const subscribe = (listener) =>
      ctx.onEvent ? ctx.onEvent(PROGRESS_EVENT, (event) => listener(event?.payload)) : noop;
    ctx.registerMany([
      {
        id: 'case-pane',
        area: sdk.PANES_AREA,
        title: 'ClaimCoach',
        data: { placement: 'right', width: '380px' },
        render: () => jsx(CasePane, { rest, subscribe }),
      },
      {
        id: 'dashboard',
        area: sdk.ROUTES_AREA,
        title: 'ClaimCoach dashboard',
        data: { path: DASHBOARD_PATH },
        render: () => jsx(DashboardPage, { rest }),
      },
      {
        id: 'nav',
        area: sdk.SIDEBAR_NAV_AREA,
        data: { path: DASHBOARD_PATH, label: 'ClaimCoach', codicon: 'checklist' },
      },
      {
        id: 'local-only',
        area: sdk.STATUSBAR_AREAS.right,
        order: 120,
        render: () => jsx(LocalOnlyIndicator, { rest }),
      },
    ]);
    // Feature-detected: hosts older than the settings-pages API still load the plugin (PC-3).
    ctx.registerSettingsPage?.({
      id: 'settings',
      title: 'ClaimCoach',
      icon: 'gear',
      render: () => jsx(SettingsPage, { rest }),
    });
  },
};

export default plugin;
