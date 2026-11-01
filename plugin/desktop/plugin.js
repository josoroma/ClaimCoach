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
 * name and ticks the approval; it says where the de-identified file was written), US-11.1 (a
 * Payer calls section attaches a recorded payer call to the open case and queues it for the
 * after-hours window; each call shows its transcription state, then the reference number and the
 * rep's instructions read from its transcript, for the biller to check, and the transcript),
 * US-10.1 (the pane is a case list view above the case detail view: the list shows the profile's
 * cases without case content and opens one in the detail view; a backend error renders an error
 * state with Retry), US-10.2 (the statusbar item's typed `IndicatorState`, local-only by default),
 * US-10.3 (the settings page shows model status, corpus status, and the retention period, which
 * the biller changes and saves), US-10.4 (the settings page previews a local corpus bundle file,
 * then imports it into the global corpus only when the manager confirms).
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
 *   outcome?: OutcomeView, closed?: true, calls?: CallView[] }} ReadyState
 * @typedef {'none' | 'queued' | 'running' | 'done' | 'failed'} CallState
 * @typedef {{ text: string, referenceNumber: string | null, instructions: string[],
 *   truncated: boolean }} TranscriptView
 * @typedef {{ callId: string, label: string, state: CallState,
 *   window: { start: number, end: number } | null, errorCode: string | null,
 *   transcript?: TranscriptView }} CallView
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
 * @typedef {'new' | 'extracted' | 'diagnosed' | 'drafted'} CaseStep
 * @typedef {{ caseId: string, openedOn: string, step: CaseStep, closed: boolean, purged: boolean,
 *   outcome: Outcome | null, documents: number, calls: number }} CaseRow
 * @typedef {{ state: 'loading' } | { state: 'ok', cases: CaseRow[] } | { state: 'unavailable' }}
 *   CaseListState
 * @typedef {{ open: (caseId: string) => void, changed: () => void,
 *   drop: (files: ArrayLike<PickedFile> | null | undefined) => void }} PaneLink
 * @typedef {'local-only' | 'richer-access'} IndicatorState
 * @typedef {{ role: string, state: string, weights: string, venv: boolean }} ModelRow
 * @typedef {{ state: 'loading' } | { state: 'ok', models: ModelRow[] } | { state: 'unavailable' }}
 *   ModelsState
 * @typedef {{ cases: number, documents: number, encrypted: boolean, available: boolean }} ScopeView
 * @typedef {{ state: 'loading' } | { state: 'ok', global: ScopeView, user: ScopeView | null }
 *   | { state: 'unavailable' }} CorpusState
 * @typedef {{ state: 'loading' } | { state: 'ok', days: number } | { state: 'invalid' }
 *   | { state: 'unavailable' }} RetentionState
 * @typedef {{ state: 'saving' } | { state: 'saved', days: number } | { state: 'refused', code: string }
 *   | { state: 'failed' }} SaveResult
 * @typedef {{ items: number, byKind: Record<string, number>, payers: string[], morePayers: number,
 *   stale: number, replaces: number, replaced: string[] }} BundleSummary
 * @typedef {{ state: 'idle' } | { state: 'checking' } | { state: 'invalid', problem: string }
 *   | { state: 'preview', upload: DocumentUpload, summary: BundleSummary } | { state: 'importing' }
 *   | { state: 'imported', imported: Record<string, number> }
 *   | { state: 'failed', code: string | null, upload?: DocumentUpload }} ImportState
 */

/** Largest file the backend accepts (US-5.1); bigger ones are refused before they are read. */
export const MAX_FILE_BYTES = 16 * 1024 * 1024;

/** Largest call recording the backend accepts (US-11.1). */
export const MAX_CALL_BYTES = 128 * 1024 * 1024;

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
  unsaved_draft: 'Save the draft edits before opening another case.',
  unsupported_audio: 'ClaimCoach accepts WAV, MP3, FLAC, and M4A call recordings only.',
  call_too_large: 'That recording is too large. ClaimCoach accepts recordings up to 128 MiB.',
  call_not_found: 'That call recording is no longer in the case; refresh the case.',
  transcription_failed: 'The call could not be transcribed; queue it again.',
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
    /** The profile's newest cases, without case content (US-10.1). */
    listCases: () => rest('/cases'),
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
     * @param {DocumentUpload} upload
     */
    uploadCall: (caseId, upload) => rest(`${casePath(caseId)}/calls`, { method: 'POST', upload }),
    /**
     * @param {string} caseId
     * @param {string} callId
     */
    transcribeCall: (caseId, callId) =>
      rest(`${casePath(caseId)}/calls/${encodeURIComponent(callId)}/transcribe`, {
        method: 'POST',
        body: {},
      }),
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

const CALL_STATES = new Set(['queued', 'running', 'done', 'failed']);
const isHour = (/** @type {unknown} */ value) =>
  Number.isInteger(value) &&
  /** @type {number} */ (value) >= 0 &&
  /** @type {number} */ (value) < 24;

/**
 * A call's transcript, when it is a well-formed one (US-11.1).
 *
 * @param {unknown} value
 * @returns {TranscriptView | null}
 */
function transcriptOf(value) {
  const transcript =
    /** @type {{ text?: unknown, reference_number?: unknown, rep_instructions?: unknown,
     *   truncated?: unknown } | null} */ (value);
  if (typeof transcript?.text !== 'string') return null;
  const reference = transcript.reference_number;
  return {
    text: transcript.text,
    referenceNumber: typeof reference === 'string' ? reference : null,
    instructions: stringsOf(transcript.rep_instructions),
    truncated: transcript.truncated === true,
  };
}

/**
 * A case body's payer calls (US-11.1); malformed entries are skipped.
 *
 * @param {unknown} body
 * @returns {CallView[]}
 */
export function callsOf(body) {
  const list = /** @type {{ calls?: unknown } | null} */ (body)?.calls;
  if (!Array.isArray(list)) return [];
  return list.flatMap((entry) => {
    const call = /** @type {{ recording?: { call_id?: unknown, filename?: unknown } | null,
     *   transcription?: { state?: unknown, error_code?: unknown,
     *     window?: { start_hour?: unknown, end_hour?: unknown } | null } | null,
     *   transcript?: unknown }} */ (entry);
    const callId = call?.recording?.call_id;
    if (typeof callId !== 'string') return [];
    const filename = call.recording?.filename;
    const job = call.transcription;
    const transcript = transcriptOf(call.transcript);
    // A finished job is forgotten after 30 days; its transcript stays with the case.
    const state =
      typeof job?.state === 'string' && CALL_STATES.has(job.state)
        ? job.state
        : transcript
          ? 'done'
          : 'none';
    const start = job?.window?.start_hour;
    const end = job?.window?.end_hour;
    /** @type {CallView} */
    const view = {
      callId,
      label: typeof filename === 'string' ? filename : 'Call recording',
      state: /** @type {CallState} */ (state),
      window: isHour(start) && isHour(end) ? { start: Number(start), end: Number(end) } : null,
      errorCode: typeof job?.error_code === 'string' ? job.error_code : null,
    };
    if (transcript) view.transcript = transcript;
    return [view];
  });
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
  const calls = callsOf(body);
  if (calls.length > 0) ready.calls = calls;
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
 * Attach a recorded payer call to the open case, then reopen it (US-11.1). A recording over the
 * backend's limit is refused here, before the webview reads it.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {PickedFile} file
 * @returns {Promise<CaseState>}
 */
export async function addCall(api, caseId, file) {
  if ((file.size ?? 0) > MAX_CALL_BYTES) return reopenWith(api, caseId, 'call_too_large');
  try {
    const bytes = await file.arrayBuffer();
    const contentType = file.type || 'application/octet-stream';
    await api.uploadCall(caseId, { filename: file.name, contentType, bytes });
  } catch (error) {
    const notice = refusalOf(error);
    return notice === null ? { state: 'unavailable', caseId } : reopenWith(api, caseId, notice);
  }
  return openCase(api, caseId);
}

/**
 * Queue a call for after-hours transcription, then reopen the case to show its job (US-11.1).
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @param {string} callId
 * @returns {Promise<CaseState>}
 */
export async function queueTranscription(api, caseId, callId) {
  try {
    await api.transcribeCall(caseId, callId);
  } catch (error) {
    const notice = refusalOf(error);
    return notice === null ? { state: 'unavailable', caseId } : reopenWith(api, caseId, notice);
  }
  return openCase(api, caseId);
}

/** @param {number} hour */
const clockHour = (hour) => `${String(hour).padStart(2, '0')}:00`;

/**
 * Where a call's transcription is, in the biller's words (US-11.1).
 *
 * @param {CallView} call
 * @returns {string}
 */
export function describeCall(call) {
  switch (call.state) {
    case 'queued': {
      const hours = call.window
        ? ` (${clockHour(call.window.start)} to ${clockHour(call.window.end)})`
        : '';
      return `Queued for transcription after hours${hours}, on this Mac.`;
    }
    case 'running':
      return 'Transcribing on this Mac…';
    case 'done':
      return 'Transcribed on this Mac.';
    case 'failed': {
      const notice = known(call.errorCode) ?? 'transcription_failed';
      return `Not transcribed: ${REFUSALS[notice]}`;
    }
    default:
      return 'Not transcribed yet.';
  }
}

/**
 * One call's transcript notes: the reference number and the rep's instructions, read by fixed
 * rules for the biller to check, then the transcript itself.
 *
 * @param {TranscriptView} transcript
 */
function TranscriptNotes(transcript) {
  return [
    transcript.truncated
      ? jsx('p', {
          role: 'alert',
          children:
            'The transcript stops before the call ended (about 30 minutes is the most it ' +
            'holds); the reference number may be missing. Check the recording.',
        })
      : null,
    jsx('p', {
      children: transcript.referenceNumber
        ? `Reference number: ${transcript.referenceNumber}`
        : 'No reference number was heard; check the transcript.',
    }),
    transcript.instructions.length
      ? jsx('ul', {
          'aria-label': 'Rep instructions',
          children: transcript.instructions.map((text, index) =>
            jsx('li', { children: text }, String(index)),
          ),
        })
      : jsx('p', { children: 'No rep instructions were heard; check the transcript.' }),
    jsx('p', { children: 'Read from the transcript on this Mac; check them against it.' }),
    jsxs('details', {
      children: [
        jsx('summary', { children: 'Transcript' }),
        jsx('p', { children: transcript.text }),
      ],
    }),
  ];
}

/**
 * The case's recorded payer calls (US-11.1): attach a recording, queue it for the after-hours
 * window, and read what its transcript says. Nothing here plays, sends, or shares a recording.
 *
 * @param {{ calls: CallView[], disabled: boolean, closed: boolean,
 *   onAttach: (files: ArrayLike<PickedFile> | null) => void,
 *   onTranscribe: (callId: string) => void }} props
 */
export function CallsPanel({ calls, disabled, closed, onAttach, onTranscribe }) {
  return jsxs('section', {
    'aria-label': 'Payer calls',
    children: [
      jsx('h3', { children: 'Payer calls' }),
      jsx('input', {
        type: 'file',
        'aria-label': 'Attach a call recording',
        accept: '.wav,.mp3,.flac,.m4a',
        disabled: disabled || closed,
        onChange: (
          /** @type {{ currentTarget: { files: ArrayLike<PickedFile> | null } }} */ event,
        ) => onAttach(event.currentTarget.files),
      }),
      calls.length === 0
        ? jsx('p', {
            children: 'No recorded calls. Attach one to have it transcribed after hours.',
          })
        : jsx('ul', {
            'aria-label': 'Recorded calls',
            children: calls.map((call) =>
              jsxs(
                'li',
                {
                  children: [
                    jsx('p', { children: call.label }),
                    jsx('p', { role: 'status', children: describeCall(call) }),
                    jsx('button', {
                      type: 'button',
                      disabled:
                        disabled || closed || call.state === 'queued' || call.state === 'running',
                      onClick: () => onTranscribe(call.callId),
                      children:
                        call.state === 'none'
                          ? 'Transcribe after hours'
                          : 'Transcribe again after hours',
                    }),
                    ...(call.transcript ? TranscriptNotes(call.transcript) : []),
                  ],
                },
                call.callId,
              ),
            ),
          }),
    ],
  });
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
 * The case detail view. The whole view is the drop zone; the file input, the paste box, and a drop
 * all add to the open case, or start one. Processing progress arrives through `subscribe`. The
 * case list opens a case through `link.open`; the view calls `link.changed` when it moves to
 * another case, so the list shows a new one (US-10.1).
 *
 * @param {{ rest: RestFn, subscribe?: SubscribeFn, link?: PaneLink }} props
 */
export function CasePane({
  rest,
  subscribe = noEvents,
  link = { open: noop, changed: noop, drop: noop },
}) {
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
          link.changed(); // a new case appears in the list
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
  /** @param {{ preventDefault: () => void, stopPropagation?: () => void,
   *   dataTransfer: { files: ArrayLike<PickedFile> } | null }} event */
  const onDrop = (event) => {
    event.preventDefault(); // keep the webview from opening the file
    event.stopPropagation?.(); // the pane's own drop zone (US-10.1) would add it twice
    addPicked(event.dataTransfer?.files);
  };
  link.drop = addPicked; // a drop on the case list joins the open case too
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
  /** @param {ArrayLike<PickedFile> | null} files */
  const onCallFile = (files) => {
    const file = Array.from(files ?? [])[0];
    if (current.state !== 'ready' || closed || !file) return;
    settle(addCall(api, current.caseId, file));
  };
  /** @param {string} callId */
  const onTranscribe = (callId) => {
    if (current.state !== 'ready' || closed) return;
    settle(queueTranscription(api, current.caseId, callId));
  };
  const onRefresh = () => {
    if (life.caseId === null || current.state === 'busy') return;
    follow(null, 'extract');
    setEdits({});
    settle(openCase(api, life.caseId));
  };
  // The case list opens a case here, through this view's own action queue (US-10.1).
  link.open = (caseId) => {
    if (current.state === 'busy') return;
    if (current.state === 'ready' && unsaved(current.draft, letter)) {
      setCurrent({ ...current, notice: 'unsaved_draft' }); // the editor keeps the text
      return;
    }
    follow(null, 'extract');
    setEdits({});
    // A failed open still names the case, so the next document or Refresh goes to it.
    settle(
      openCase(api, caseId).then((next) =>
        next.state === 'unavailable' ? { state: 'unavailable', caseId } : next,
      ),
    );
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
      jsx(CallsPanel, {
        calls: current.state === 'ready' ? (current.calls ?? []) : [],
        disabled: current.state !== 'ready',
        closed,
        onAttach: onCallFile,
        onTranscribe,
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
 * The local-only statusbar item (US-3.5, US-10.2), refreshed every `SETTINGS_REFRESH_MS`.
 *
 * @param {{ rest: RestFn }} props
 */
export function LocalOnlyIndicator({ rest }) {
  const [state, setState] = useState(/** @type {IndicatorState} */ ('local-only'));
  useEffect(() => {
    let current = true;
    const refresh = () => {
      loadIndicatorState(rest).then((next) => {
        if (current) setState(next);
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
  const view = indicatorView(state);
  return jsx('span', { 'data-state': state, title: view.title, children: view.label });
}

/**
 * The statusbar item's text for a state (US-10.2). Both states run on local models only: richer
 * access changes what the agent may be given later, not where models run.
 *
 * @param {IndicatorState} state
 * @returns {{ label: string, title: string }}
 */
export function indicatorView(state) {
  const base = 'ClaimCoach runs on local models only. Case content never leaves this Mac.';
  if (state === 'richer-access') {
    return {
      label: 'Local-only · richer agent access on',
      title: `${base} Richer agent access is on; agent tool results are still redacted.`,
    };
  }
  return { label: 'Local-only', title: base };
}

/**
 * The statusbar item's state: `richer-access` only for an explicit `true` (US-10.2).
 *
 * @param {RestFn} rest
 * @returns {Promise<IndicatorState>}
 */
export async function loadIndicatorState(rest) {
  return (await loadRicherAccess(rest)) ? 'richer-access' : 'local-only';
}

/** Fixed text per code a retention save may be refused with (BR-14). */
export const SETTINGS_REFUSALS = Object.freeze({
  invalid_request: 'Enter a whole number of days from 1 to 3650.',
  settings_unavailable: 'Settings are saved only inside Hermes; nothing was saved.',
  settings_managed: 'An administrator manages this setting; nothing was saved.',
});

/**
 * The model status rows of a `GET /models/status` body, or `null` when it is not one (US-10.3).
 *
 * @param {unknown} body
 * @returns {ModelRow[] | null}
 */
export function modelsOf(body) {
  const answer = /** @type {{ ok?: unknown, models?: unknown } | null} */ (body);
  if (answer?.ok !== true || !Array.isArray(answer.models)) return null;
  return answer.models.flatMap((entry) => {
    const model =
      /** @type {{ role?: unknown, state?: unknown, weights?: unknown, venv_present?: unknown }} */ (
        entry
      );
    if (
      typeof model?.role !== 'string' ||
      typeof model.state !== 'string' ||
      typeof model.weights !== 'string'
    ) {
      return [];
    }
    return [
      {
        role: model.role,
        state: model.state,
        weights: model.weights,
        venv: model.venv_present === true,
      },
    ];
  });
}

/**
 * @param {unknown} value
 * @returns {ScopeView | null}
 */
function scopeOf(value) {
  const scope =
    /** @type {{ cases?: unknown, documents?: unknown, encrypted?: unknown, available?: unknown }
     *   | null} */ (value);
  if (typeof scope?.encrypted !== 'boolean') return null;
  return {
    cases: isCount(scope.cases) ? Number(scope.cases) : 0,
    documents: isCount(scope.documents) ? Number(scope.documents) : 0,
    encrypted: scope.encrypted,
    available: scope.available !== false,
  };
}

/**
 * The global scope and this profile's user scope of a `GET /corpus/status` body (US-10.3).
 *
 * @param {unknown} body
 * @returns {{ global: ScopeView, user: ScopeView | null } | null}
 */
export function corpusOf(body) {
  const answer =
    /** @type {{ ok?: unknown, global_scope?: unknown, user_scopes?: unknown } | null} */ (body);
  const global = scopeOf(answer?.global_scope);
  if (answer?.ok !== true || global === null) return null;
  const users = Array.isArray(answer.user_scopes) ? answer.user_scopes : [];
  return { global, user: scopeOf(users[0]) };
}

/**
 * Read one settings-page section; any failure reads as `unavailable` (BR-14).
 *
 * @template T
 * @param {() => Promise<unknown>} read
 * @param {(body: unknown) => T | null} parse
 * @returns {Promise<{ state: 'ok', value: T } | { state: 'unavailable' }>}
 */
async function loadSection(read, parse) {
  try {
    const value = parse(await read());
    return value === null ? { state: 'unavailable' } : { state: 'ok', value };
  } catch {
    return { state: 'unavailable' };
  }
}

/**
 * @param {RestFn} rest
 * @returns {Promise<ModelsState>}
 */
export async function loadModels(rest) {
  const section = await loadSection(() => rest('/models/status'), modelsOf);
  return section.state === 'ok' ? { state: 'ok', models: section.value } : section;
}

/**
 * @param {RestFn} rest
 * @returns {Promise<CorpusState>}
 */
export async function loadCorpus(rest) {
  const section = await loadSection(() => rest('/corpus/status'), corpusOf);
  return section.state === 'ok' ? { state: 'ok', ...section.value } : section;
}

/**
 * @param {unknown} body
 * @returns {number | null}
 */
function retentionOf(body) {
  const answer = /** @type {{ ok?: unknown, retention_days?: unknown } | null} */ (body);
  return answer?.ok === true && isDays(answer.retention_days)
    ? Number(answer.retention_days)
    : null;
}

/**
 * The stored period of a `GET /settings` body: days, `invalid` when the stored value is invalid
 * (the purge skips the profile), or `null` when the body is not settings.
 *
 * @param {unknown} body
 * @returns {number | 'invalid' | null}
 */
function storedPeriodOf(body) {
  const answer = /** @type {{ ok?: unknown, retention_days?: unknown } | null} */ (body);
  if (answer?.ok === true && answer.retention_days === null) return 'invalid';
  return retentionOf(body);
}

/** @param {unknown} value */
const isDays = (value) =>
  Number.isInteger(value) &&
  /** @type {number} */ (value) >= 1 &&
  /** @type {number} */ (value) <= 3650;

/**
 * @param {RestFn} rest
 * @returns {Promise<RetentionState>}
 */
export async function loadRetention(rest) {
  const section = await loadSection(() => rest('/settings'), storedPeriodOf);
  if (section.state !== 'ok') return section;
  return section.value === 'invalid' ? { state: 'invalid' } : { state: 'ok', days: section.value };
}

/**
 * The days the biller typed, or `null` unless a whole number from 1 to 3650.
 *
 * @param {string} text
 * @returns {number | null}
 */
export function parseDays(text) {
  const trimmed = text.trim();
  if (!/^\d{1,4}$/.test(trimmed)) return null;
  const days = Number(trimmed);
  return isDays(days) ? days : null;
}

/**
 * Save the retention period (US-10.3); the worker's next purge reads it.
 *
 * @param {RestFn} rest
 * @param {number} days
 * @returns {Promise<SaveResult>}
 */
export async function saveRetention(rest, days) {
  try {
    const saved = retentionOf(
      await rest('/settings/retention', { method: 'POST', body: { retention_days: days } }),
    );
    return saved === null ? { state: 'failed' } : { state: 'saved', days: saved };
  } catch (error) {
    const code = codeOf(error);
    return code === null ? { state: 'failed' } : { state: 'refused', code };
  }
}

/**
 * @param {SaveResult} result
 * @returns {string}
 */
export function describeSave(result) {
  switch (result.state) {
    case 'saving':
      return 'Saving…';
    case 'saved':
      return `Saved. The next purge removes the content of cases closed more than ${result.days} days ago.`;
    case 'refused':
      return Object.hasOwn(SETTINGS_REFUSALS, result.code)
        ? SETTINGS_REFUSALS[/** @type {keyof typeof SETTINGS_REFUSALS} */ (result.code)]
        : 'The retention period was not saved.';
    default:
      return 'The retention period was not saved. Check that ClaimCoach is enabled.';
  }
}

const SECTION_UNAVAILABLE =
  'Unavailable. Check that the ClaimCoach backend and worker are running.';

/**
 * Each model role's server state, weights, and venv (US-2.2 to US-2.4).
 *
 * @param {ModelsState} models
 */
export function ModelsSection(models) {
  const body =
    models.state === 'ok'
      ? jsx('ul', {
          'aria-label': 'Model roles',
          children: models.models.map((model) =>
            jsx(
              'li',
              {
                children:
                  `${model.role}: ${model.state} · weights ${model.weights} · ` +
                  `venv ${model.venv ? 'ready' : 'missing'}`,
              },
              model.role,
            ),
          ),
        })
      : jsx('p', {
          role: models.state === 'loading' ? 'status' : 'alert',
          children: models.state === 'loading' ? 'Loading model status…' : SECTION_UNAVAILABLE,
        });
  return jsxs('section', {
    'aria-label': 'Models',
    children: [jsx('h3', { children: 'Models' }), body],
  });
}

/**
 * The global corpus and this profile's case store (US-4.1, US-4.2).
 *
 * @param {CorpusState} corpus
 */
export function CorpusSection(corpus) {
  /** @type {unknown[]} */
  let lines;
  if (corpus.state === 'ok') {
    const { global, user } = corpus;
    lines = [
      jsx('p', {
        children: global.available
          ? `Global corpus: ${global.documents} document(s).`
          : 'Global corpus: could not be opened.',
      }),
      jsx('p', {
        children:
          user === null
            ? 'Your case store: none yet; it is created with your first case.'
            : user.available
              ? `Your case store: ${user.cases} case(s), ${user.documents} document(s), ` +
                `${user.encrypted ? 'encrypted' : 'not encrypted'} at rest.`
              : 'Your case store: could not be opened (its key is missing or wrong).',
      }),
    ];
  } else {
    lines = [
      jsx('p', {
        role: corpus.state === 'loading' ? 'status' : 'alert',
        children: corpus.state === 'loading' ? 'Loading corpus status…' : SECTION_UNAVAILABLE,
      }),
    ];
  }
  return jsxs('section', {
    'aria-label': 'Corpus',
    children: [jsx('h3', { children: 'Corpus' }), ...lines],
  });
}

/**
 * The retention period with an input and Save (US-4.5, US-10.3).
 *
 * @param {{ retention: RetentionState, draft: string | null, result: SaveResult | null,
 *   onDraft: (text: string) => void, onSave: () => void }} props
 */
export function RetentionSection({ retention, draft, result, onDraft, onSave }) {
  const stored = retention.state === 'ok' ? retention.days : null;
  const days = draft === null ? stored : parseDays(draft);
  const status =
    retention.state === 'ok'
      ? `Closed cases keep their content for ${retention.days} days, then it is purged.`
      : retention.state === 'invalid'
        ? 'The stored retention period is invalid, so no closed case is purged; save a valid one.'
        : retention.state === 'loading'
          ? 'Loading the retention period…'
          : SECTION_UNAVAILABLE;
  return jsxs('section', {
    'aria-label': 'Retention',
    children: [
      jsx('h3', { children: 'Retention' }),
      jsx('p', { role: 'status', children: status }),
      jsx('input', {
        type: 'number',
        'aria-label': 'Retention period in days',
        min: 1,
        max: 3650,
        value: draft ?? (stored === null ? '' : String(stored)),
        disabled: stored === null && retention.state !== 'invalid',
        onChange: (/** @type {{ currentTarget: { value: string } }} */ event) =>
          onDraft(event.currentTarget.value),
      }),
      jsx('button', {
        type: 'button',
        disabled: days === null || days === stored || result?.state === 'saving',
        onClick: onSave,
        children: 'Save',
      }),
      jsx('p', {
        children:
          'A shorter period purges more closed cases at the next purge (within six hours); ' +
          'purged content cannot be restored.',
      }),
      result ? jsx('p', { role: 'status', children: describeSave(result) }) : null,
    ],
  });
}

/**
 * The ClaimCoach settings page (US-1.4, US-10.3, US-10.4): worker status, models, corpus,
 * retention, and the global corpus import.
 * Each section loads on its own, so a stopped worker still leaves retention editable.
 *
 * @param {{ rest: RestFn }} props
 */
export function SettingsPage({ rest }) {
  const [models, setModels] = useState(/** @type {ModelsState} */ ({ state: 'loading' }));
  const [corpus, setCorpus] = useState(/** @type {CorpusState} */ ({ state: 'loading' }));
  const [retention, setRetention] = useState(/** @type {RetentionState} */ ({ state: 'loading' }));
  const [draft, setDraft] = useState(/** @type {string | null} */ (null));
  const [result, setResult] = useState(/** @type {SaveResult | null} */ (null));
  // A saved period wins over a first read that answers after the save.
  const [life] = useState({ live: true, saved: false });
  const [corpusImport, setImport] = useState(/** @type {ImportState} */ ({ state: 'idle' }));
  // The last pick or cancel wins: a slower answer about an earlier file is dropped.
  const [picks] = useState({ last: 0 });
  useEffect(() => {
    life.live = true;
    loadModels(rest).then((next) => life.live && setModels(next));
    loadCorpus(rest).then((next) => life.live && setCorpus(next));
    loadRetention(rest).then((next) => life.live && !life.saved && setRetention(next));
    return () => {
      life.live = false;
    };
  }, [rest, life]);
  const onSave = () => {
    const days = draft === null ? null : parseDays(draft);
    if (days === null || result?.state === 'saving') return;
    setResult({ state: 'saving' });
    saveRetention(rest, days).then((saved) => {
      if (!life.live) return;
      setResult(saved);
      if (saved.state === 'saved') {
        life.saved = true;
        setRetention({ state: 'ok', days: saved.days });
        setDraft(null);
      }
    });
  };
  /** @param {Promise<ImportState>} pending */
  const follow = (pending) => {
    picks.last += 1;
    const pick = picks.last;
    pending.then((next) => {
      if (!life.live || pick !== picks.last) return;
      setImport(next);
      // After any import attempt: a failed or slow one may still have stored the bundle.
      if (next.state === 'imported' || (next.state === 'failed' && next.upload)) {
        loadCorpus(rest).then((c) => life.live && setCorpus(c));
      }
    });
  };
  /** @param {ArrayLike<PickedFile> | null} files */
  const onPick = (files) => {
    const file = Array.from(files ?? [])[0];
    if (!file || corpusImport.state === 'importing') return;
    setImport({ state: 'checking' });
    follow(checkBundle(rest, file));
  };
  const onImport = () => {
    // From the preview, or Try again after a failed import of the same file.
    const upload =
      corpusImport.state === 'preview' || corpusImport.state === 'failed'
        ? corpusImport.upload
        : undefined;
    if (upload === undefined) return;
    setImport({ state: 'importing' });
    follow(importBundle(rest, upload));
  };
  const onCancel = () => {
    picks.last += 1; // an answer still on its way is dropped
    setImport({ state: 'idle' });
  };
  return jsxs('section', {
    'aria-label': 'ClaimCoach settings',
    children: [
      jsx('h2', { children: 'ClaimCoach' }),
      jsx(WorkerStatus, { rest }),
      ModelsSection(models),
      CorpusSection(corpus),
      jsx(RetentionSection, { retention, draft, result, onDraft: setDraft, onSave }),
      jsx(CorpusImportSection, { state: corpusImport, onPick, onImport, onCancel }),
    ],
  });
}

/** Largest corpus bundle the backend accepts (US-4.3); a bigger file is refused before it is read. */
export const MAX_BUNDLE_BYTES = 5 * 1024 * 1024;
/**
 * How long the pane waits for an import: a minute past the gateway's own 15 minutes, so the
 * gateway answers first (the embedding model may load and embed thousands of chunks).
 */
export const IMPORT_TIMEOUT_MS = 960_000;

const KIND_NAMES = Object.freeze({
  rule_card: 'rule card(s)',
  code: 'code(s)',
  letter_template: 'letter template(s)',
});
const KIND_SINGULAR = Object.freeze({
  rule_card: 'rule card',
  code: 'code',
  letter_template: 'letter template',
});

/** Fixed text per code an import may be refused with (BR-14). */
const IMPORT_REFUSALS = Object.freeze({
  invalid_bundle: 'The file is not a valid corpus bundle; nothing was imported.',
  import_not_confirmed: 'The import was not confirmed; nothing was imported.',
  index_stale: 'The corpus index was built with another embedding model; reindex it first.',
  model_unavailable: 'The embedding model is missing or not responding; nothing was imported.',
  model_busy: 'The local models are busy; import again in a moment.',
  worker_unavailable: 'The ClaimCoach worker is not running; start it and pick the file again.',
});

/**
 * Counts per kind, in words.
 *
 * @param {Record<string, number>} counts
 * @returns {string}
 */
function kindsInWords(counts) {
  return Object.entries(counts)
    .map(([kind, n]) => {
      const name = Object.hasOwn(KIND_NAMES, kind)
        ? KIND_NAMES[/** @type {keyof typeof KIND_NAMES} */ (kind)]
        : kind;
      return `${n} ${name}`;
    })
    .join(', ');
}

/**
 * @param {unknown} value
 * @returns {Record<string, number>}
 */
function countsByKind(value) {
  if (value === null || typeof value !== 'object') return {};
  return Object.fromEntries(Object.entries(value).filter(([, n]) => isCount(n)));
}

/**
 * A `POST /corpus/import/preview` answer (US-10.4), or `null` when the body is not one.
 *
 * @param {unknown} body
 * @returns {{ valid: true, summary: BundleSummary } | { valid: false, problem: string } | null}
 */
export function previewOf(body) {
  const answer = /** @type {{ ok?: unknown, valid?: unknown, problem?: unknown, items?: unknown,
   *   by_kind?: unknown, payers?: unknown, more_payers?: unknown, stale?: unknown,
   *   replaces?: unknown, replaced?: unknown } | null} */ (body);
  if (answer?.ok !== true || typeof answer.valid !== 'boolean') return null;
  if (!answer.valid) {
    const problem = typeof answer.problem === 'string' ? answer.problem : 'invalid bundle';
    return { valid: false, problem };
  }
  return {
    valid: true,
    summary: {
      items: isCount(answer.items) ? Number(answer.items) : 0,
      byKind: countsByKind(answer.by_kind),
      payers: stringsOf(answer.payers),
      morePayers: isCount(answer.more_payers) ? Number(answer.more_payers) : 0,
      stale: isCount(answer.stale) ? Number(answer.stale) : 0,
      replaces: isCount(answer.replaces) ? Number(answer.replaces) : 0,
      replaced: stringsOf(answer.replaced),
    },
  };
}

/**
 * Preview a picked bundle file (US-10.4); nothing is imported. A file over the limit is refused
 * before it is read.
 *
 * @param {RestFn} rest
 * @param {PickedFile} file
 * @returns {Promise<ImportState>}
 */
export async function checkBundle(rest, file) {
  if ((file.size ?? 0) > MAX_BUNDLE_BYTES) {
    return { state: 'invalid', problem: 'bundle is larger than 5 MiB' };
  }
  try {
    const bytes = await file.arrayBuffer();
    const upload = {
      filename: file.name,
      contentType: file.type || 'application/octet-stream',
      bytes,
    };
    const preview = previewOf(await rest('/corpus/import/preview', { method: 'POST', upload }));
    if (preview === null) return { state: 'failed', code: null };
    return preview.valid
      ? { state: 'preview', upload, summary: preview.summary }
      : { state: 'invalid', problem: preview.problem };
  } catch (error) {
    return { state: 'failed', code: codeOf(error) };
  }
}

/**
 * Import a previewed bundle into the global corpus (US-10.4): the confirmed request.
 *
 * @param {RestFn} rest
 * @param {DocumentUpload} upload
 * @returns {Promise<ImportState>}
 */
export async function importBundle(rest, upload) {
  try {
    const body = /** @type {{ ok?: unknown, imported?: unknown } | null} */ (
      await rest('/corpus/import?confirm=true', {
        method: 'POST',
        upload,
        timeoutMs: IMPORT_TIMEOUT_MS,
      })
    );
    return body?.ok === true
      ? { state: 'imported', imported: countsByKind(body.imported) }
      : { state: 'failed', code: null, upload };
  } catch (error) {
    return { state: 'failed', code: codeOf(error), upload }; // kept for Try again
  }
}

/**
 * A replaced item (`rule_card Aetna/appeal_levels`) as the manager reads it.
 *
 * @param {string} entry
 * @returns {string}
 */
function replacedName(entry) {
  const [kind = '', ...key] = entry.split(' ');
  const name = Object.hasOwn(KIND_SINGULAR, kind)
    ? KIND_SINGULAR[/** @type {keyof typeof KIND_SINGULAR} */ (kind)]
    : kind;
  return [name, ...key].join(' ');
}

/**
 * Where an import is, in the manager's words.
 *
 * @param {ImportState} state
 * @returns {string}
 */
export function describeImport(state) {
  switch (state.state) {
    case 'checking':
      return 'Checking the file…';
    case 'invalid':
      return `This file is not a valid corpus bundle (${state.problem}); nothing was imported.`;
    case 'preview': {
      const { summary } = state;
      const replaced = summary.replaces
        ? ` ${summary.replaces} of them replace items already in the global corpus.`
        : ' None of them is in the global corpus yet.';
      const stale = summary.stale
        ? ` ${summary.stale} were verified more than ${STALE_AFTER_DAYS} days ago.`
        : '';
      return (
        `This bundle holds ${summary.items} item(s): ${kindsInWords(summary.byKind)}.` +
        `${replaced}${stale} Nothing is imported until you confirm.`
      );
    }
    case 'importing':
      return 'Importing into the global corpus on this Mac…';
    case 'imported':
      return `Imported ${kindsInWords(state.imported)} into the global corpus.`;
    case 'failed':
      // A stopped or slow worker may still finish an import the gateway gave up on.
      if (state.upload && (state.code === null || state.code === 'worker_unavailable')) {
        return (
          'The import may still be finishing on this Mac (a large bundle can take minutes). ' +
          'Check the Corpus section, then try again only if nothing changed.'
        );
      }
      return state.code !== null && Object.hasOwn(IMPORT_REFUSALS, state.code)
        ? IMPORT_REFUSALS[/** @type {keyof typeof IMPORT_REFUSALS} */ (state.code)]
        : 'The bundle was not imported. Check that ClaimCoach and its worker are running.';
    default:
      return '';
  }
}

/**
 * The global corpus import (US-10.4): pick a local bundle file, read what it holds and replaces,
 * then import it into the global corpus or cancel. Nothing is written before the confirmation.
 *
 * @param {{ state: ImportState, onPick: (files: ArrayLike<PickedFile> | null) => void,
 *   onImport: () => void, onCancel: () => void }} props
 */
export function CorpusImportSection({ state, onPick, onImport, onCancel }) {
  const working = state.state === 'checking' || state.state === 'importing';
  const preview = state.state === 'preview' ? state.summary : null;
  const payers = preview?.payers.length
    ? `Payers: ${preview.payers.join(', ')}${preview.morePayers ? ` and ${preview.morePayers} more` : ''}.`
    : null;
  const more = preview ? preview.replaces - preview.replaced.length : 0;
  const replaced = preview?.replaced.length
    ? `Replaces: ${preview.replaced.map(replacedName).join(', ')}${more > 0 ? ` and ${more} more` : ''}.`
    : null;
  const retry = state.state === 'failed' && state.upload !== undefined;
  return jsxs('section', {
    'aria-label': 'Global corpus import',
    children: [
      jsx('h3', { children: 'Global corpus import' }),
      jsx('p', {
        children:
          'Import a corpus bundle (.yaml, .yml, or .json, up to 5 MiB) from this Mac. Every ' +
          'profile on this Mac uses the global corpus; items with the same key are replaced.',
      }),
      jsx('input', {
        type: 'file',
        'aria-label': 'Pick a corpus bundle',
        accept: '.yaml,.yml,.json',
        disabled: working,
        onChange: (
          /** @type {{ currentTarget: { files: ArrayLike<PickedFile> | null, value: string } }} */ event,
        ) => {
          const files = Array.from(event.currentTarget.files ?? []);
          // Cleared, so picking the same file again (fixed, or after Cancel) is a change too.
          event.currentTarget.value = '';
          onPick(files);
        },
      }),
      state.state === 'idle' ? null : jsx('p', { role: 'status', children: describeImport(state) }),
      payers ? jsx('p', { children: payers }) : null,
      replaced ? jsx('p', { 'aria-label': 'Replaced items', children: replaced }) : null,
      preview
        ? jsx('button', {
            type: 'button',
            onClick: onImport,
            children: 'Import into the global corpus',
          })
        : null,
      preview ? jsx('button', { type: 'button', onClick: onCancel, children: 'Cancel' }) : null,
      retry ? jsx('button', { type: 'button', onClick: onImport, children: 'Try again' }) : null,
    ],
  });
}

/** Fixed text when the case list cannot be read (BR-14: never the backend's own text). */
export const CASE_LIST_UNAVAILABLE =
  'Cases could not be loaded. Check that the ClaimCoach backend and worker are running.';

const STEPS = Object.freeze({
  new: 'New',
  extracted: 'Fields read',
  diagnosed: 'Diagnosed',
  drafted: 'Appeal drafted',
});

/**
 * The rows of a `GET /cases` body, or `null` when it is not one (US-10.1). No case content.
 *
 * @param {unknown} body
 * @returns {CaseRow[] | null}
 */
export function casesOf(body) {
  const answer = /** @type {{ ok?: unknown, cases?: unknown } | null} */ (body);
  if (answer?.ok !== true || !Array.isArray(answer.cases)) return null;
  return answer.cases.flatMap((entry) => {
    const row = /** @type {{ case_id?: unknown, opened_at?: unknown, closed_at?: unknown,
     *   purged_at?: unknown, outcome?: unknown, documents?: unknown, calls?: unknown,
     *   extracted?: unknown, diagnosed?: unknown, drafted?: unknown } | null} */ (entry);
    if (typeof row?.case_id !== 'string' || typeof row.opened_at !== 'string') return [];
    const outcome =
      typeof row.outcome === 'string' && Object.hasOwn(OUTCOMES, row.outcome)
        ? /** @type {Outcome} */ (row.outcome)
        : null;
    /** @type {CaseStep} */
    const step =
      row.drafted === true
        ? 'drafted'
        : row.diagnosed === true
          ? 'diagnosed'
          : row.extracted === true
            ? 'extracted'
            : 'new';
    return [
      {
        caseId: row.case_id,
        openedOn: localDay(row.opened_at),
        step,
        closed: typeof row.closed_at === 'string',
        purged: typeof row.purged_at === 'string',
        outcome,
        documents: isCount(row.documents) ? Number(row.documents) : 0,
        calls: isCount(row.calls) ? Number(row.calls) : 0,
      },
    ];
  });
}

/**
 * An ISO timestamp's date on this Mac's calendar; the date part as sent when it does not parse.
 *
 * @param {string} timestamp
 * @returns {string}
 */
function localDay(timestamp) {
  const when = new Date(timestamp);
  return Number.isNaN(when.getTime()) ? timestamp.slice(0, 10) : isoToday(when);
}

/**
 * One case-list row in words.
 *
 * @param {CaseRow} row
 * @returns {string}
 */
export function describeCaseRow(row) {
  const parts = [`opened ${row.openedOn}`, STEPS[row.step], `${row.documents} document(s)`];
  if (row.calls > 0) parts.push(`${row.calls} call(s)`);
  if (row.outcome) parts.push(OUTCOMES[row.outcome]);
  if (row.purged) parts.push('content purged');
  else if (row.closed) parts.push('closed');
  return `${row.caseId}: ${parts.join(' · ')}`;
}

/**
 * Read the case list; any failure, an envelope included, reads as `unavailable`.
 *
 * @param {CaseApi} api
 * @returns {Promise<CaseListState>}
 */
export async function loadCaseList(api) {
  const section = await loadSection(api.listCases, casesOf);
  return section.state === 'ok' ? { state: 'ok', cases: section.value } : section;
}

/**
 * The case list view (US-10.1): the profile's newest cases; selecting one opens it in the detail
 * view through `link.open`. The detail view reloads the list through `link.changed`.
 *
 * @param {{ rest: RestFn, link: PaneLink }} props
 */
export function CaseListView({ rest, link }) {
  const api = createCaseApi(rest);
  const [list, setList] = useState(/** @type {CaseListState} */ ({ state: 'loading' }));
  // The last read wins; a read answered after unmount is dropped.
  const [life] = useState({ live: true, read: 0 });
  const reload = () => {
    life.read += 1;
    const read = life.read;
    loadCaseList(api).then((next) => {
      if (life.live && read === life.read) setList(next);
    });
  };
  link.changed = reload;
  useEffect(() => {
    life.live = true;
    reload();
    return () => {
      life.live = false;
    };
  }, [rest, life]);
  const body =
    list.state === 'loading'
      ? jsx('p', { role: 'status', children: 'Loading cases…' })
      : list.state === 'unavailable'
        ? jsx('p', { role: 'alert', children: CASE_LIST_UNAVAILABLE })
        : list.cases.length === 0
          ? jsx('p', { children: 'No cases yet. Drop a denial document below to start one.' })
          : jsx('ul', {
              'aria-label': 'Cases',
              children: list.cases.map((row) =>
                jsx(
                  'li',
                  {
                    children: jsx('button', {
                      type: 'button',
                      onClick: () => link.open(row.caseId),
                      children: describeCaseRow(row),
                    }),
                  },
                  row.caseId,
                ),
              ),
            });
  return jsxs('nav', {
    'aria-label': 'Case list',
    children: [
      jsx('h3', { children: 'Cases' }),
      body,
      jsx('button', {
        type: 'button',
        onClick: reload,
        children: list.state === 'unavailable' ? 'Retry' : 'Refresh list',
      }),
    ],
  });
}

/**
 * The registered pane (US-10.1): the case list view above the case detail view, joined by one
 * link object that lives as long as the pane. A drop anywhere on it goes to the detail view.
 *
 * @param {{ rest: RestFn, subscribe?: SubscribeFn }} props
 */
export function ClaimCoachPane({ rest, subscribe = noEvents }) {
  const [link] = useState(/** @type {PaneLink} */ ({ open: noop, changed: noop, drop: noop }));
  return jsxs('div', {
    'aria-label': 'ClaimCoach',
    // The whole pane is the drop zone: a file dropped on the list must never open in the webview.
    onDragOver: (/** @type {{ preventDefault: () => void }} */ event) => event.preventDefault(),
    onDrop: (
      /** @type {{ preventDefault: () => void,
       *   dataTransfer: { files: ArrayLike<PickedFile> } | null }} */ event,
    ) => {
      event.preventDefault();
      link.drop(event.dataTransfer?.files);
    },
    children: [jsx(CaseListView, { rest, link }), jsx(CasePane, { rest, subscribe, link })],
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
        render: () => jsx(ClaimCoachPane, { rest, subscribe }),
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
