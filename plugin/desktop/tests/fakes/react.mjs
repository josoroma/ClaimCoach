/**
 * Fake `react` whose hooks run synchronously, so a component can be called as a function and its
 * state updates and effect cleanups observed without a renderer. US-1.4.
 */
export const hooks = { states: [], cleanups: [] };

export function resetHooks() {
  hooks.states = [];
  hooks.cleanups = [];
}

export function useState(initial) {
  const slot = { value: initial, updates: [] };
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
