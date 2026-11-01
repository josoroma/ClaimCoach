/**
 * node --test suite for the shared logo on the plugin pages. US-13.1 scenarios:
 *   - The plugin pages show the shared logo
 *   - The logo does not repeat the heading to screen readers
 * The file's own contract (self-contained SVG) is tests/test_us_13_1_shared_logo.py.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { CasePane, ClaimCoachLogo, DashboardPage, LOGO, SettingsPage } from '../plugin.js';
import { resetHooks, runCleanups } from './fakes/react.mjs';

const LOGO_FILE = new URL('../../assets/claimcoach-logo.svg', import.meta.url);
const rest = async () => ({});

beforeEach(resetHooks);
afterEach(runCleanups);

const ATTRIBUTE = /\s*([a-zA-Z-]+)="([^"]*)"/y;
const ROOT_ATTRIBUTES = ['xmlns', 'viewBox', 'width', 'height', 'role', 'aria-labelledby'];

/** Read every `name="value"` of an element's attribute text; fail on anything else in it. */
export function readAttributes(body) {
  const attrs = {};
  ATTRIBUTE.lastIndex = 0;
  let match = ATTRIBUTE.exec(body);
  while (match) {
    attrs[match[1]] = match[2];
    if (ATTRIBUTE.lastIndex === body.length) return attrs;
    match = ATTRIBUTE.exec(body);
  }
  assert.fail(`unread attribute text: ${body}`);
}

/**
 * Every element of the logo file, read exhaustively: the root's attributes, the title, and each
 * drawn shape. Anything left over (another element, a closing tag, a stray attribute) fails.
 */
export function readLogo(svg) {
  const root = /^<svg\b([^>]*)>([\s\S]*)<\/svg>\s*$/.exec(svg);
  assert.ok(root, 'one <svg> element and nothing around it');
  const rest = root[2].replace(/<title\b[^>]*>[^<]*<\/title>/, '');
  const shapes = [];
  const leftover = rest.replace(/<(rect|path)\b([^>]*?)\/>/g, (_, tag, body) => {
    shapes.push({ tag, attrs: readAttributes(body) });
    return '';
  });
  assert.equal(leftover.trim(), '', 'nothing in the file but its title and the shapes');
  return { root: readAttributes(root[1]), shapes };
}

/** The logo element leading a page's heading, and the heading's text. */
function headingOf(page) {
  const heading = page.props.children[0];
  const [logo, text] = heading.props.children;
  return { heading, logo, text };
}

const PAGES = [
  ['case pane', () => CasePane({ rest }), 'h2', 'ClaimCoach'],
  ['manager dashboard', () => DashboardPage({ rest }), 'h1', 'ClaimCoach dashboard'],
  ['settings page', () => SettingsPage({ rest }), 'h2', 'ClaimCoach'],
];

describe('US-13.1 shared logo', () => {
  // --- Scenario: The plugin pages show the shared logo ---
  test('test_us_13_1_pages_show_logo', () => {
    for (const [name, render, level, title] of PAGES) {
      resetHooks();
      const { heading, logo, text } = headingOf(render());
      assert.equal(heading.type, level, name);
      assert.equal(logo.type, ClaimCoachLogo, `${name} leads its heading with the logo`);
      assert.equal(text, title, name);
    }
  });

  test('test_us_13_1_logo_matches_file', async () => {
    const file = readLogo(await readFile(LOGO_FILE, 'utf8'));
    assert.deepEqual(Object.keys(file.root), ROOT_ATTRIBUTES, 'nothing on the root restyles it');
    assert.equal(file.root.viewBox, LOGO.viewBox);
    assert.deepEqual(
      LOGO.shapes.map((shape) => ({ tag: shape.tag, attrs: { ...shape.attrs } })),
      file.shapes,
      'plugin.js draws exactly the shapes and colors of plugin/assets/claimcoach-logo.svg',
    );
    const drawn = ClaimCoachLogo({});
    assert.equal(drawn.type, 'svg');
    assert.equal(drawn.props.viewBox, LOGO.viewBox);
    assert.equal(drawn.props.width, 20, 'the default size');
    assert.deepEqual(
      drawn.props.children.map((child) => child.type),
      file.shapes.map((shape) => shape.tag),
    );
    const check = drawn.props.children.at(-1).props;
    assert.equal(check.strokeWidth, '5', 'SVG attributes reach React in camelCase');
    assert.equal(check.strokeLinejoin, 'round');
    assert.equal(check.d, file.shapes.at(-1).attrs.d);
    assert.equal(ClaimCoachLogo({ size: 28 }).props.height, 28);
  });

  test('test_us_13_1_logo_match_refuses_extra_content', async () => {
    const svg = await readFile(LOGO_FILE, 'utf8');
    const red = svg.replace('</svg>', '<path d="M0 0h64v64H0z" fill="#FF0000"></path></svg>');
    assert.throws(
      () => readLogo(red),
      /nothing in the file but/,
      'an extra, non-self-closing shape',
    );
    const faded = svg.replace('rx="14"', 'rx="14" opacity=\'0.2\'');
    assert.throws(() => readLogo(faded), /unread attribute text/, 'a single-quoted attribute');
    const tinted = svg.replace('<svg ', '<svg style="filter:hue-rotate(180deg)" ');
    assert.notDeepEqual(Object.keys(readLogo(tinted).root), ROOT_ATTRIBUTES, 'a restyled root');
    assert.throws(() => readLogo(`<g>${svg}</g>`), /one <svg> element/);
  });

  // --- Scenario: The logo does not repeat the heading to screen readers ---
  test('test_us_13_1_logo_hidden_from_screen_readers', () => {
    for (const [name, render] of PAGES) {
      resetHooks();
      const { logo } = headingOf(render());
      const drawn = logo.type(logo.props);
      assert.equal(drawn.props['aria-hidden'], 'true', name);
      assert.equal(drawn.props.focusable, 'false', name);
      assert.equal(drawn.props['aria-label'], undefined, `${name}: the heading names the page`);
      assert.equal(drawn.props.role, undefined, name);
    }
  });
});
