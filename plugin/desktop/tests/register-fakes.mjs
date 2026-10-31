/**
 * Resolve the three specifiers plugin.js may import (PC-3) to local fakes, so `node --test` runs
 * the plugin without Hermes Desktop or React. Loaded with `node --import`. US-1.4.
 */
import { registerHooks } from 'node:module';

const fakes = new Map([
  ['@hermes/plugin-sdk', new URL('./fakes/plugin-sdk.mjs', import.meta.url).href],
  ['react', new URL('./fakes/react.mjs', import.meta.url).href],
  ['react/jsx-runtime', new URL('./fakes/jsx-runtime.mjs', import.meta.url).href],
]);

registerHooks({
  resolve(specifier, context, nextResolve) {
    const url = fakes.get(specifier);
    return url ? { url, shortCircuit: true } : nextResolve(specifier, context);
  },
});
