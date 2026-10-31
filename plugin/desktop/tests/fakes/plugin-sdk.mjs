/**
 * Fake `@hermes/plugin-sdk`: area constants with the values the SDK docs list (US-1.4), a `host`
 * that records every property access (US-3.3: the pane must never touch it), and US-7.2's
 * `captureGatewayFileDownload`, which a test installs or removes with `setFileDownload` (older
 * hosts lack it).
 */
export const PANES_AREA = 'panes';
export const ROUTES_AREA = 'routes';
export const SIDEBAR_NAV_AREA = 'sidebar.nav';
export const SETTINGS_PLUGINS_AREA = 'settings.plugins';
export const STATUSBAR_AREAS = Object.freeze({ left: 'statusbar.left', right: 'statusbar.right' });

/**
 * Fake agent sessions: the transcript a cloud model would see. US-3.3 checks it never changes.
 */
export const sessions = {
  s1: { messages: [{ role: 'user', content: 'What does CO-197 mean?' }], toolCalls: [] },
};

export const hostAccesses = [];

function recorder(path) {
  return new Proxy(() => {}, {
    get(_target, key) {
      if (typeof key === 'symbol') return undefined;
      hostAccesses.push(`${path}.${key}`);
      return recorder(`${path}.${key}`);
    },
    apply() {
      hostAccesses.push(`${path}()`);
      return undefined;
    },
  });
}

export const host = recorder('host');

/** @type {(() => (path: string, suggestedName: string) => Promise<void>) | undefined} */
export let captureGatewayFileDownload;

/** Install (or, with `undefined`, remove) the host's file-save capture. */
export function setFileDownload(capture) {
  captureGatewayFileDownload = capture;
}
