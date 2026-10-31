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
 * extracted fields are listed with unreadable ones highlighted, and the biller confirms values).
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
 * @typedef {{ state: 'ready', caseId: string, documents: DocumentView[], fields: FieldView[],
 *   otherClaims?: number, unreadSources?: number, notice?: Refusal }} ReadyState
 * @typedef {{ state: 'idle', notice?: Refusal } | { state: 'busy' } | ReadyState
 *   | { state: 'processing', caseId: string, progress: number }
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
  model_unavailable: 'The local extraction model is missing or not responding.',
  model_busy: 'The local models are busy; process the case again in a moment.',
  extraction_failed: 'The documents could not be read; enter the fields by hand.',
  worker_unavailable: 'The ClaimCoach worker stopped; start it and process the case again.',
  job_not_found: 'Processing stopped before it finished; process the case again.',
  processing_timeout: 'Processing took too long and was stopped; process the case again.',
});

/** Field and list names as the pane shows them. */
const FIELD_NAMES = Object.freeze({
  payer_name: 'Payer',
  claim_id: 'Claim number',
  billed_amount: 'Billed',
  paid_amount: 'Paid',
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
 * Start the pipeline for a case. Progress arrives as `plugin.claimcoach.case.progress` events.
 *
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export async function processCase(api, caseId) {
  try {
    await api.processCase(caseId);
    return { state: 'processing', caseId, progress: 0 };
  } catch (error) {
    const notice = refusalOf(error);
    return notice === null ? { state: 'unavailable' } : reopenWith(api, caseId, notice);
  }
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
        ? `: ${pending} field(s) need confirmation.`
        : current.fields?.length
          ? ': every field is read or confirmed.'
          : ' is ready to process.';
      return `${notice}Case ${current.caseId}${next}${unread}${others}`;
    }
    case 'processing':
      return `Processing case ${current.caseId} on this Mac… ${Math.round((current.progress ?? 0) * 100)}%`;
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
     *   processing: string | null, onProgress: (payload: unknown) => void }} */ ({
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
      setCurrent(next);
    });
  };
  life.onProgress = (payload) => {
    const progress = progressOf(payload);
    const caseId = life.processing;
    if (!life.live || progress === null || caseId === null || progress.caseId !== caseId) return;
    if (progress.stage === 'done' || progress.stage === 'failed') {
      life.processing = null;
      setEdits({}); // fresh values replace anything typed before the run
      const notice = known(progress.errorCode) ?? 'extraction_failed';
      settle(progress.stage === 'done' ? openCase(api, caseId) : reopenWith(api, caseId, notice));
    } else {
      setCurrent({ state: 'processing', caseId, progress: progress.progress });
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
    life.processing = current.caseId;
    settle(processCase(api, current.caseId));
  };
  const onRefresh = () => {
    if (life.caseId === null || current.state === 'busy') return;
    life.processing = null;
    setEdits({});
    settle(openCase(api, life.caseId));
  };
  const onNewCase = () => {
    life.action += 1; // an upload still running no longer updates the pane
    life.caseId = null;
    life.processing = null;
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
