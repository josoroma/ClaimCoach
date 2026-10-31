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
 * once passed, or why it is unknown; the denial date is a field the biller confirms).
 * Rules: PC-1 (opt-in: `defaultEnabled: false`), PC-3 (imports only
 * `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`; optional SDK calls are feature-detected),
 * PC-4, BR-2 (case data goes pane → `ctx.rest` → plugin_api → worker, never the agent transcript),
 * BR-14 (error text from the backend is never shown; a refusal shows a fixed message per code).
 *
 * The views are placeholders until EPIC-10 (US-10.1..US-10.3) builds them; they already show the
 * worker status so a user can tell whether the backend half is enabled.
 */
import { PANES_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk';
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
 * @typedef {{ state: 'ready', caseId: string, documents: DocumentView[], fields: FieldView[],
 *   otherClaims?: number, unreadSources?: number, notice?: Refusal,
 *   diagnosis?: DiagnosisView, deadline?: DeadlineView }} ReadyState
 * @typedef {{ state: 'idle', notice?: Refusal } | { state: 'busy' } | ReadyState
 *   | { state: 'processing', caseId: string, progress: number, diagnosing?: true }
 *   | { state: 'unavailable', caseId?: string }} CaseState
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
});

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
 * A processing state; one without `diagnosing` is an extraction (US-5.2).
 *
 * @param {string} caseId
 * @param {number} progress
 * @param {boolean} diagnosing
 * @returns {CaseState}
 */
function processing(caseId, progress, diagnosing) {
  return diagnosing
    ? { state: 'processing', caseId, progress, diagnosing: true }
    : { state: 'processing', caseId, progress };
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
    const body = await start(caseId);
    const kind = /** @type {{ kind?: unknown } | null} */ (body)?.kind;
    return processing(caseId, 0, kind === 'diagnose');
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
      return `${notice}Case ${current.caseId}${next}${unread}${others}${stale}`;
    }
    case 'processing': {
      const verb = current.diagnosing ? 'Diagnosing' : 'Processing';
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
     *   processing: string | null, diagnosing?: boolean,
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
    pending.then((next) => {
      if (!life.live || action !== life.action) return;
      // The last case this pane worked on stays open across failures, so the next document
      // joins it instead of starting a second case. Values typed for another case are dropped.
      if ('caseId' in next && next.caseId) {
        if (next.caseId !== life.caseId) setEdits({});
        life.caseId = next.caseId;
      }
      // The job that runs may be another kind than the one asked for (one job per case).
      if (next.state === 'processing') follow(next.caseId, next.diagnosing === true);
      setCurrent(next);
    });
  };
  /**
   * Follow a job's events from now on: called before its start request is sent, so an event that
   * arrives before the answer is not missed.
   *
   * @param {string | null} caseId
   * @param {boolean} diagnosing
   */
  const follow = (caseId, diagnosing) => {
    life.processing = caseId;
    life.diagnosing = diagnosing;
  };
  life.onProgress = (payload) => {
    const progress = progressOf(payload);
    const caseId = life.processing;
    if (!life.live || progress === null || caseId === null || progress.caseId !== caseId) return;
    if (progress.stage === 'done' || progress.stage === 'failed') {
      const diagnosing = life.diagnosing === true;
      follow(null, false);
      setEdits({}); // fresh values replace anything typed before the run
      const notice =
        known(progress.errorCode) ?? (diagnosing ? 'diagnosis_failed' : 'extraction_failed');
      const chained = life.action + 1; // the action settle starts next
      settle(
        progress.stage === 'failed'
          ? reopenWith(api, caseId, notice)
          : diagnosing
            ? openCase(api, caseId)
            : afterExtraction(api, caseId, () => {
                if (!life.live || life.action !== chained) return false;
                follow(caseId, true);
                return true;
              }),
      );
    } else {
      setCurrent(processing(caseId, progress.progress, life.diagnosing === true));
    }
  };
  /** @param {ArrayLike<PickedFile> | null | undefined} files */
  const addPicked = (files) => {
    const picked = Array.from(files ?? []);
    if (picked.length === 0 || current.state === 'busy') return;
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
    follow(current.caseId, false);
    settle(processCase(api, current.caseId));
  };
  const onDiagnose = () => {
    if (current.state !== 'ready') return;
    follow(current.caseId, true);
    settle(diagnoseCase(api, current.caseId));
  };
  const onRefresh = () => {
    if (life.caseId === null || current.state === 'busy') return;
    follow(null, false);
    setEdits({});
    settle(openCase(api, life.caseId));
  };
  const onNewCase = () => {
    life.action += 1; // an upload still running no longer updates the pane
    life.caseId = null;
    follow(null, false);
    setEdits({});
    setCurrent({ state: 'idle' });
  };
  /** @param {{ currentTarget: { value: string } }} event */
  const onDraft = (event) => setDraft(event.currentTarget.value);
  const onPaste = () => {
    const text = draft;
    if (!text.trim() || current.state === 'busy') return;
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
        disabled: current.state === 'busy',
        onChange: onFile,
      }),
      jsx('p', { role: 'status', children: describeCase(current) }),
      jsx('button', {
        type: 'button',
        disabled: current.state !== 'ready',
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
        disabled: current.state === 'busy',
        onChange: onDraft,
      }),
      jsx('button', {
        type: 'button',
        disabled: current.state === 'busy' || !draft.trim(),
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
        disabled: current.state !== 'ready',
      }),
      jsx('button', {
        type: 'button',
        disabled: current.state !== 'ready' || !current.fields?.length,
        onClick: onDiagnose,
        children: 'Diagnose case',
      }),
      DeadlineLine(current.state === 'ready' ? current.deadline : undefined, isoToday()),
      DiagnosisPanel(current.state === 'ready' ? current.diagnosis : undefined),
    ],
  });
}

export function DashboardPage() {
  return jsxs('section', {
    'aria-label': 'ClaimCoach manager dashboard',
    children: [
      jsx('h1', { children: 'ClaimCoach dashboard' }),
      jsx('p', { children: 'De-identified outcome statistics appear here.' }),
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
        area: PANES_AREA,
        title: 'ClaimCoach',
        data: { placement: 'right', width: '380px' },
        render: () => jsx(CasePane, { rest, subscribe }),
      },
      {
        id: 'dashboard',
        area: ROUTES_AREA,
        title: 'ClaimCoach dashboard',
        data: { path: DASHBOARD_PATH },
        render: () => jsx(DashboardPage, {}),
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: DASHBOARD_PATH, label: 'ClaimCoach', codicon: 'checklist' },
      },
      {
        id: 'local-only',
        area: STATUSBAR_AREAS.right,
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
