/**
 * node --test suite for the statusbar item. US-3.5 scenarios:
 *   - Richer access is off by default (as the desktop half reads it)
 *   - Statusbar reflects richer access
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, { LocalOnlyIndicator, loadRicherAccess, SETTINGS_REFRESH_MS } from '../plugin.js';
import { byArea, createFakeCtx } from './fake_ctx.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const settings = (richer) => async (path) =>
  path === '/settings' ? { ok: true, richer_agent_access: richer } : { ok: true };

beforeEach(resetHooks);
afterEach(runCleanups);

/** Render the registered statusbar item, let its request settle, and re-render with the result. */
async function renderStatusbar(rest) {
  const ctx = createFakeCtx({ rest });
  plugin.register(ctx);
  const item = byArea(ctx.recorded)['statusbar.right'][0];
  const element = item.render();
  element.type(element.props);
  await tick();
  const updates = hooks.states[0].updates;
  hooks.seed = updates.length > 0 ? [updates.at(-1)] : [];
  return { ctx, rendered: element.type(element.props) };
}

describe('US-3.5 statusbar', () => {
  test('test_us_3_5_statusbar_reflects_richer_access', async () => {
    const { ctx, rendered } = await renderStatusbar(settings(true));
    // The fake useEffect runs on every render; React would fetch once. Only /settings is read.
    assert.deepEqual(new Set(ctx.recorded.restCalls), new Set(['/settings']));
    assert.equal(rendered.props.children, 'Local-only · richer agent access on');
    assert.match(rendered.props.title, /Richer agent access is on/);
    assert.match(rendered.props.title, /still redacted/);
  });

  test('test_us_3_5_richer_access_off_by_default_in_statusbar', async () => {
    const { rendered } = await renderStatusbar(settings(false));
    assert.equal(rendered.props.children, 'Local-only');
    assert.doesNotMatch(rendered.props.title, /Richer/);
  });

  test('anything but an explicit true reads as off', async () => {
    assert.equal(await loadRicherAccess(settings('yes')), false);
    assert.equal(await loadRicherAccess(async () => null), false);
    assert.equal(
      await loadRicherAccess(async () => ({ ok: false, richer_agent_access: true })),
      false,
    );
    assert.equal(
      await loadRicherAccess(async () => {
        throw new Error('404');
      }),
      false,
    );
  });

  test('test_us_3_5_statusbar_follows_a_changed_setting', async (t) => {
    t.mock.timers.enable({ apis: ['setInterval'] });
    let stored = false;
    const rest = async () => ({ ok: true, richer_agent_access: stored });
    LocalOnlyIndicator({ rest });
    await tick();
    stored = true; // the user flips it in Settings → Plugins
    t.mock.timers.tick(SETTINGS_REFRESH_MS);
    await tick();
    stored = false;
    t.mock.timers.tick(SETTINGS_REFRESH_MS);
    await tick();
    assert.deepEqual(hooks.states[0].updates, [false, true, false]);
    runCleanups();
    t.mock.timers.tick(SETTINGS_REFRESH_MS);
    await tick();
    assert.equal(hooks.states[0].updates.length, 3, 'no refresh after unmount');
  });

  test('a settings answer after unmount is ignored', async () => {
    LocalOnlyIndicator({ rest: settings(true) });
    runCleanups();
    await tick();
    assert.deepEqual(hooks.states[0].updates, []);
  });
});
