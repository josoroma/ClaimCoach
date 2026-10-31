/**
 * Fake Hermes `PluginContext` that records contributions instead of mounting them. US-1.4; US-3.3
 * records each REST request with its method and options.
 *
 * @param {{ settingsPages?: boolean, rest?: (path: string, opts?: object) => Promise<unknown> }} [options]
 */
export function createFakeCtx({ settingsPages = true, rest = async () => ({}) } = {}) {
  const recorded = { contributions: [], settingsPages: [], restCalls: [], restRequests: [] };
  const ctx = {
    source: 'plugin:claimcoach',
    recorded,
    register(contribution) {
      recorded.contributions.push(contribution);
      return () => {};
    },
    registerMany(contributions) {
      recorded.contributions.push(...contributions);
      return () => {};
    },
    rest(path, opts) {
      recorded.restCalls.push(path);
      recorded.restRequests.push({ path, method: opts?.method ?? 'GET', opts });
      return rest(path, opts);
    },
    onDispose() {},
  };
  if (settingsPages) {
    ctx.registerSettingsPage = (page) => {
      recorded.settingsPages.push(page);
      return () => {};
    };
  }
  return ctx;
}

/** @param {{ contributions: Array<{ area: string }> }} recorded */
export function byArea(recorded) {
  return Object.groupBy(recorded.contributions, (c) => c.area);
}
