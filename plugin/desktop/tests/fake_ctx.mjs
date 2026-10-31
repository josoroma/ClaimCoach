/**
 * Fake Hermes `PluginContext` that records contributions instead of mounting them. US-1.4.
 *
 * @param {{ settingsPages?: boolean, rest?: (path: string) => Promise<unknown> }} [options]
 */
export function createFakeCtx({ settingsPages = true, rest = async () => ({}) } = {}) {
  const recorded = { contributions: [], settingsPages: [], restCalls: [] };
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
    rest(path) {
      recorded.restCalls.push(path);
      return rest(path);
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
