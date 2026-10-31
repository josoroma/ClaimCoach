/** Fake `react/jsx-runtime`: elements are plain `{ type, props }` records tests can inspect. US-1.4. */
export function jsx(type, props) {
  return { type, props };
}

export const jsxs = jsx;
export const Fragment = Symbol.for('react.fragment');
