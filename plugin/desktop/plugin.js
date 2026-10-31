// @ts-check
/**
 * ClaimCoach desktop half: case pane, manager dashboard route, local-only statusbar item, and
 * settings page. Plain ESM, no build step, no JSX (PC-3).
 *
 * Implements: US-1.1 (package layout), US-1.4 (registration contract and allowed imports), US-3.3
 * (the case API client wraps only `ctx.rest`; the pane never touches `host`, the composer, or
 * agent sessions), US-3.5 (the statusbar item shows when richer agent access is on). Rules: PC-1 (opt-in: `defaultEnabled: false`), PC-3 (imports only
 * `@hermes/plugin-sdk`, `react`, `react/jsx-runtime`; optional SDK calls are feature-detected),
 * PC-4, BR-2 (case data goes pane → `ctx.rest` → plugin_api → worker, never the agent transcript),
 * BR-14 (error text from the backend is never shown).
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
 * @typedef {{ name: string, type: string, arrayBuffer: () => Promise<ArrayBuffer> }} PickedFile
 * @typedef {{ state: 'idle' } | { state: 'busy' } | { state: 'ready', caseId: string }
 *   | { state: 'processing', caseId: string } | { state: 'unavailable' }} CaseState
 */

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
    /** @param {string} caseId */
    processCase: (caseId) => rest(`${casePath(caseId)}/process`, { method: 'POST', body: {} }),
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
 * Create a case, upload one document into it, and open it. Any failure (backend half disabled,
 * route not available yet, error envelope) reads as `unavailable`; its text is never shown.
 *
 * @param {CaseApi} api
 * @param {PickedFile} file
 * @returns {Promise<CaseState>}
 */
export async function uploadCase(api, file) {
  try {
    const caseId = caseIdOf(await api.createCase());
    if (caseId === null) return { state: 'unavailable' };
    const bytes = await file.arrayBuffer();
    const contentType = file.type || 'application/octet-stream';
    await api.uploadDocument(caseId, { filename: file.name, contentType, bytes });
    return await openCase(api, caseId);
  } catch {
    return { state: 'unavailable' };
  }
}

/**
 * @param {CaseApi} api
 * @param {string} caseId
 * @returns {Promise<CaseState>}
 */
export async function openCase(api, caseId) {
  try {
    return caseIdOf(await api.getCase(caseId)) === caseId
      ? { state: 'ready', caseId }
      : { state: 'unavailable' };
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
    return { state: 'processing', caseId };
  } catch {
    return { state: 'unavailable' };
  }
}

/**
 * @param {CaseState} current
 * @returns {string}
 */
export function describeCase(current) {
  switch (current.state) {
    case 'idle':
      return 'Drop a denial document (EOB, ERA, or payer letter) to start a case.';
    case 'busy':
      return 'Uploading…';
    case 'ready':
      return `Case ${current.caseId} is ready to process.`;
    case 'processing':
      return `Processing case ${current.caseId} on this Mac…`;
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
 * @param {{ rest: RestFn }} props
 */
export function CasePane({ rest }) {
  const api = createCaseApi(rest);
  const [current, setCurrent] = useState(/** @type {CaseState} */ ({ state: 'idle' }));
  // One object per mounted pane: answers that arrive after unmount, or after a newer action
  // started, are dropped (the last action wins, never the slowest one).
  const [life] = useState({ live: true, action: 0 });
  useEffect(() => {
    life.live = true;
    return () => {
      life.live = false;
    };
  }, [life]);
  /** @param {Promise<CaseState>} pending */
  const settle = (pending) => {
    life.action += 1;
    const action = life.action;
    setCurrent({ state: 'busy' });
    pending.then((next) => {
      if (life.live && action === life.action) setCurrent(next);
    });
  };
  /** @param {{ currentTarget: { files: ArrayLike<PickedFile> | null } }} event */
  const onFile = (event) => {
    const file = event.currentTarget.files?.[0];
    if (!file || current.state === 'busy') return;
    settle(uploadCase(api, file));
  };
  const onProcess = () => {
    if (current.state === 'ready') settle(processCase(api, current.caseId));
  };
  return jsxs('section', {
    'aria-label': 'ClaimCoach cases',
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
    ctx.registerMany([
      {
        id: 'case-pane',
        area: PANES_AREA,
        title: 'ClaimCoach',
        data: { placement: 'right', width: '380px' },
        render: () => jsx(CasePane, { rest }),
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
