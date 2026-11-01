/**
 * The control walk of the no-send checks (US-7.3, US-7.4): every string a rendered control shows
 * or acts on, and every link or form target, so a test can assert none sends to a payer (BR-4).
 */

/** Words of a control that sends, submits, or files something with a payer (BR-4). */
export const SEND =
  /(re)?send|\bsent\b|submit|fax|e-?mail|mailto|transmit|deliver|upload(?:ing)? to|(?:to|with) (?:the )?payer|portal|clearinghouse|file with/i;
/** A link or form target that leaves the app: any scheme, or a protocol-relative URL. */
export const ABSOLUTE = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;
const CONTROLS = new Set(['button', 'a', 'form', 'input', 'textarea', 'select', 'option']);
/** Props whose text names what a control does; `value` only where it is the control's label. */
const LABEL_PROPS = ['title', 'name', 'placeholder', 'alt', 'label'];
const LABEL_VALUES = new Set(['button', 'option']);

/** Expand a function component, a `memo`, or a `forwardRef` into what it renders. */
function expand(node) {
  const { type, props } = node;
  if (typeof type === 'function') return type(props);
  if (type && typeof type === 'object') {
    if (typeof type.render === 'function') return type.render(props, null);
    if (type.type) return { type: type.type, props };
  }
  return undefined;
}

/**
 * Walk a rendered tree and collect every string a control or a label shows or acts on: all text
 * inside a control or a `<label>`, its label props and `aria-*` text, and every link or form
 * target.
 */
export function controlStrings(
  node,
  out = { strings: [], links: [], controls: 0 },
  inside = false,
) {
  if (node === null || node === undefined || typeof node === 'boolean') return out;
  if (typeof node !== 'object') {
    if (inside) out.strings.push(String(node));
    return out;
  }
  if (Array.isArray(node)) {
    for (const child of node) controlStrings(child, out, inside);
    return out;
  }
  const expanded = expand(node);
  if (expanded !== undefined) return controlStrings(expanded, out, inside);
  const props = node.props ?? {};
  const control = CONTROLS.has(node.type) || Boolean(props.onClick || props.onSubmit);
  if (control && !inside) out.controls += 1;
  const labelled = inside || control || node.type === 'label';
  if (labelled) {
    const keys = [
      ...LABEL_PROPS,
      ...(LABEL_VALUES.has(node.type) ? ['value'] : []),
      ...Object.keys(props).filter((key) => key.startsWith('aria-')),
    ];
    for (const key of keys) {
      if (typeof props[key] === 'string') out.strings.push(props[key]);
    }
  }
  for (const key of ['href', 'action', 'formAction']) {
    if (typeof props[key] === 'string') out.links.push(props[key]);
  }
  if (node.type === 'form') out.strings.push('<form>');
  controlStrings(props.children, out, labelled);
  return out;
}
