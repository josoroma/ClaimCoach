/**
 * Fake `react` whose hooks run synchronously, so a component can be called as a function and its
 * state updates and effect cleanups observed without a renderer. US-1.4; US-3.3 adds `seed` to
 * re-render a component from a given state.
 */
export const hooks = { states: [], cleanups: [], seed: [] };

export function resetHooks() {
  hooks.states = [];
  hooks.cleanups = [];
  hooks.seed = [];
}

/** Run (and forget) every effect cleanup, as an unmount would: stops timers effects started. */
export function runCleanups() {
  for (const cleanup of hooks.cleanups.splice(0)) cleanup();
}

/** `hooks.seed` holds values the next `useState` calls return instead of their initial value. */
export function useState(initial) {
  const slot = { value: hooks.seed.length > 0 ? hooks.seed.shift() : initial, updates: [] };
  hooks.states.push(slot);
  return [
    slot.value,
    (next) => {
      slot.value = next;
      slot.updates.push(next);
    },
  ];
}

export function useEffect(effect) {
  const cleanup = effect();
  if (typeof cleanup === 'function') hooks.cleanups.push(cleanup);
}
