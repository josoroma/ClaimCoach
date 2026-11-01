import { hooks } from './fakes/react.mjs';

/**
 * Fake Hermes `PluginContext` that records contributions instead of mounting them. US-1.4; US-3.3
 * records each REST request with its method and options; US-5.2 adds `onEvent` (with `events`),
 * whose listeners `emit(type, payload)` calls the way the gateway event stream would.
 *
 * @param {{ settingsPages?: boolean, events?: boolean,
 *   rest?: (path: string, opts?: object) => Promise<unknown> }} [options]
 */
export function createFakeCtx({
  settingsPages = true,
  events = false,
  rest = async () => ({}),
} = {}) {
  const recorded = {
    contributions: [],
    settingsPages: [],
    restCalls: [],
    restRequests: [],
    listeners: [],
  };
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
  if (events) {
    ctx.onEvent = (type, listener) => {
      const entry = { type, listener };
      recorded.listeners.push(entry);
      return () => {
        recorded.listeners.splice(recorded.listeners.indexOf(entry), 1);
      };
    };
    ctx.emit = (type, payload) => {
      for (const entry of [...recorded.listeners]) {
        if (entry.type === type) entry.listener({ type, session_id: '', payload });
      }
    };
  }
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

/**
 * The case detail view inside the registered pane (US-10.1: the pane is the case list above the
 * detail view). The wrapper's own hook slot is dropped, so tests index the detail view's hooks.
 *
 * @param {{ type: (props: object) => { props: { children: unknown[] } }, props: object }} element
 */
export function casePaneOf(element) {
  const before = hooks.states.length;
  const pane = element.type(element.props);
  hooks.states.splice(before);
  return pane.props.children[1];
}
