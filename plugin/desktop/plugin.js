// @ts-check
/**
 * ClaimCoach desktop half: case pane, manager dashboard route, local-only statusbar item, and
 * settings page. Plain ESM, no build step, no JSX (PC-3).
 *
 * Implements: US-1.1 (package layout), US-1.4 (registration contract and allowed imports).
 * Rules: PC-1 (opt-in: `defaultEnabled: false`), PC-3 (imports only `@hermes/plugin-sdk`, `react`,
 * `react/jsx-runtime`; optional SDK calls are feature-detected), BR-2 (case data goes through
 * `ctx.rest`, never the agent transcript).
 *
 * The views are placeholders until EPIC-10 (US-10.1..US-10.3) builds them; they already show the
 * worker status so a user can tell whether the backend half is enabled.
 */
import { PANES_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk';
import { useEffect, useState } from 'react';
import { jsx, jsxs } from 'react/jsx-runtime';

export const PLUGIN_ID = 'claimcoach';
export const DASHBOARD_PATH = '/claimcoach/dashboard';

/**
 * @typedef {(path: string) => Promise<unknown>} RestFn
 * @typedef {{ ok: true, status: 'ok', version: string }} HealthResponse
 * @typedef {{ state: 'loading' } | { state: 'ok', version: string } | { state: 'unavailable' }} WorkerState
 */

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
  return jsxs('section', {
    'aria-label': 'ClaimCoach cases',
    children: [jsx('h2', { children: 'ClaimCoach' }), jsx(WorkerStatus, { rest })],
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

export function LocalOnlyIndicator() {
  return jsx('span', {
    title: 'ClaimCoach runs on local models only. Case content never leaves this Mac.',
    children: 'Local-only',
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
    const rest = (path) => ctx.rest(path);
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
        render: () => jsx(LocalOnlyIndicator, {}),
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
