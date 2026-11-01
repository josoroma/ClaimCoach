/**
 * node --test suite for the settings page's global corpus import. US-10.4 scenarios:
 *   - A bundle is previewed before it is imported
 *   - The import runs only after confirmation
 *   - An invalid bundle is refused
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import {
  CorpusImportSection,
  checkBundle,
  describeImport,
  IMPORT_TIMEOUT_MS,
  importBundle,
  MAX_BUNDLE_BYTES,
  previewOf,
  SettingsPage,
} from '../plugin.js';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const BYTES = new TextEncoder().encode('items: []').buffer;
const bundleFile = {
  name: 'aetna-rules.yaml',
  type: 'application/x-yaml',
  size: 9,
  arrayBuffer: async () => BYTES,
};
const PREVIEW = {
  ok: true,
  valid: true,
  problem: null,
  items: 3,
  by_kind: { rule_card: 2, code: 1 },
  payers: ['Aetna'],
  more_payers: 0,
  stale: 1,
  replaces: 1,
  replaced: ['rule_card Aetna/timely_filing'],
};
const rejection = (status, code) =>
  new Error(`${status}: ${JSON.stringify({ ok: false, error: { code, message: 'secret text' } })}`);

/** A gateway that previews and imports, recording each request. */
function backend({ preview = PREVIEW, fail = null } = {}) {
  const requests = [];
  const rest = async (path, opts) => {
    requests.push({ path, opts });
    if (fail?.(path)) throw fail(path);
    if (path === '/corpus/import/preview') return preview;
    if (path === '/corpus/import?confirm=true') {
      return { ok: true, imported: { rule_card: 2, code: 1 }, chunks: 3 };
    }
    if (path === '/corpus/status') {
      return { ok: true, global_scope: { encrypted: false, documents: 3 }, user_scopes: [] };
    }
    if (path === '/settings') return { ok: true, retention_days: 90 };
    return {};
  };
  return { rest, requests };
}

/** Indexes of the settings page's hook slots. */
const slot = { corpus: 1, import: 6 };

function rerender(element, ...seed) {
  resetHooks();
  hooks.seed = seed;
  return element.type(element.props);
}

/** Render the page with its import section in ``state`` and return the section's props. */
function pageWith(rest, state) {
  const page = rerender(
    { type: SettingsPage, props: { rest } },
    { state: 'loading' },
    { state: 'loading' },
    { state: 'loading' },
    null,
    null,
    { live: true, saved: false },
    state,
  );
  return page.props.children[5].props;
}

const imports = () => hooks.states[slot.import].updates;

afterEach(() => runCleanups());

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-10.4 a bundle is previewed before it is imported', () => {
  test('test_us_10_4_pane_bundle_previewed', async () => {
    const { rest, requests } = backend();
    const section = pageWith(rest, { state: 'idle' });
    section.onPick([bundleFile]);
    assert.deepEqual(imports()[0], { state: 'checking' });
    await tick();
    const previewed = imports().at(-1);
    assert.equal(previewed.state, 'preview');
    const upload = requests.find((r) => r.path === '/corpus/import/preview').opts;
    assert.equal(upload.method, 'POST');
    assert.deepEqual(upload.upload, {
      filename: 'aetna-rules.yaml',
      contentType: 'application/x-yaml',
      bytes: BYTES,
    });
    assert.ok(
      requests.every((r) => r.path !== '/corpus/import?confirm=true'),
      'nothing is imported before the manager confirms',
    );

    const shown = CorpusImportSection({ ...section, state: previewed });
    const [, , input, status, payers, replaced, confirm, cancel, retry] = shown.props.children;
    assert.equal(input.props.accept, '.yaml,.yml,.json');
    assert.equal(
      status.props.children,
      'This bundle holds 3 item(s): 2 rule card(s), 1 code(s). 1 of them replace items ' +
        'already in the global corpus. 1 were verified more than 180 days ago. Nothing is ' +
        'imported until you confirm.',
    );
    assert.equal(payers.props.children, 'Payers: Aetna.');
    assert.equal(replaced.props.children, 'Replaces: rule card Aetna/timely_filing.');
    assert.equal(retry, null);
    assert.equal(confirm.props.children, 'Import into the global corpus');
    assert.equal(cancel.props.children, 'Cancel');
    assert.deepEqual(hostAccesses, []);
  });

  test('a new bundle with no payers and nothing stale', () => {
    const state = {
      state: 'preview',
      upload: {},
      summary: {
        items: 1,
        byKind: { letter_template: 1, other: 2 },
        payers: [],
        morePayers: 0,
        stale: 0,
        replaces: 0,
        replaced: [],
      },
    };
    assert.equal(
      describeImport(state),
      'This bundle holds 1 item(s): 1 letter template(s), 2 other. None of them is in the ' +
        'global corpus yet. Nothing is imported until you confirm.',
    );
    const shown = CorpusImportSection({ state, onPick() {}, onImport() {}, onCancel() {} });
    assert.equal(shown.props.children[4], null, 'no payer line');
    assert.equal(shown.props.children[5], null, 'nothing replaced');
    const many = { ...state, summary: { ...state.summary, payers: ['A', 'B'], morePayers: 3 } };
    const listed = CorpusImportSection({ state: many, onPick() {}, onImport() {}, onCancel() {} });
    assert.equal(listed.props.children[4].props.children, 'Payers: A, B and 3 more.');
  });

  test('cancel forgets the file and drops a late preview', async () => {
    let answer;
    const rest = (path) =>
      path === '/corpus/import/preview'
        ? new Promise((resolve) => {
            answer = resolve;
          })
        : Promise.resolve({});
    const section = pageWith(rest, { state: 'idle' });
    section.onPick([bundleFile]);
    await tick(); // the file is read, then the preview is asked for
    section.onCancel();
    answer(PREVIEW);
    await tick();
    assert.deepEqual(imports(), [{ state: 'checking' }, { state: 'idle' }]);
  });

  test('picking nothing, or picking while an import runs, does nothing', () => {
    const { rest } = backend();
    pageWith(rest, { state: 'idle' }).onPick(null);
    pageWith(rest, { state: 'idle' }).onPick([]);
    pageWith(rest, { state: 'importing' }).onPick([bundleFile]);
    assert.deepEqual(imports(), []);
    const shown = CorpusImportSection({
      state: { state: 'importing' },
      onPick() {},
      onImport() {},
      onCancel() {},
    });
    assert.equal(shown.props.children[2].props.disabled, true);
    assert.equal(
      shown.props.children[3].props.children,
      'Importing into the global corpus on this Mac…',
    );
    assert.equal(
      CorpusImportSection({ state: { state: 'idle' }, onPick() {}, onImport() {}, onCancel() {} })
        .props.children[3],
      null,
    );
  });

  test('the file input hands its files to the page', () => {
    const picked = [];
    const shown = CorpusImportSection({
      state: { state: 'idle' },
      onPick: (files) => picked.push(files),
      onImport() {},
      onCancel() {},
    });
    shown.props.children[2].props.onChange({ currentTarget: { files: [bundleFile] } });
    assert.deepEqual(picked, [[bundleFile]]);
  });
});

describe('US-10.4 the import runs only after confirmation', () => {
  test('test_us_10_4_pane_import_after_confirmation', async () => {
    const { rest, requests } = backend();
    const previewed = await checkBundle(rest, bundleFile);
    const section = pageWith(rest, previewed);
    section.onImport();
    assert.deepEqual(imports()[0], { state: 'importing' });
    await tick();
    const imported = requests.find((r) => r.path === '/corpus/import?confirm=true');
    assert.deepEqual(imported.opts, {
      method: 'POST',
      upload: previewed.upload,
      timeoutMs: IMPORT_TIMEOUT_MS,
    });
    assert.deepEqual(imports().at(-1), { state: 'imported', imported: { rule_card: 2, code: 1 } });
    await tick();
    assert.equal(
      hooks.states[slot.corpus].updates.at(-1).state,
      'ok',
      'the corpus section refreshes',
    );
    assert.equal(
      describeImport(imports().at(-1)),
      'Imported 2 rule card(s), 1 code(s) into the global corpus.',
    );
  });

  test('import does nothing without a preview', () => {
    const { rest, requests } = backend();
    pageWith(rest, { state: 'idle' }).onImport();
    assert.deepEqual(imports(), []);
    assert.ok(requests.every((r) => !r.path.startsWith('/corpus/import')));
  });

  test('a refused or failed import explains itself with fixed text', async () => {
    const upload = { filename: 'b.yaml', contentType: 'x', bytes: BYTES };
    for (const [code, text] of [
      ['index_stale', /reindex it first/],
      ['model_unavailable', /embedding model/],
      ['import_not_confirmed', /not confirmed/],
      ['worker_unavailable', /may still be finishing/],
      ['model_busy', /busy/],
      ['internal_error', /was not imported/],
    ]) {
      const { rest } = backend({ fail: () => rejection(409, code) });
      const failed = await importBundle(rest, upload);
      assert.deepEqual(failed, { state: 'failed', code, upload }, 'the file is kept for Try again');
      assert.match(describeImport(failed), text);
      assert.doesNotMatch(describeImport(failed), /secret text/);
    }
    const unclear = await importBundle(async () => ({ ok: false }), upload);
    assert.deepEqual(unclear, { state: 'failed', code: null, upload });
    assert.match(describeImport(unclear), /may still be finishing/);
    assert.deepEqual(
      await importBundle(async () => {
        throw new Error('offline');
      }, upload),
      { state: 'failed', code: null, upload },
    );
    assert.match(describeImport({ state: 'failed', code: 'worker_unavailable' }), /not running/);
    assert.deepEqual(
      await importBundle(
        async () => ({ ok: true, imported: { rule_card: -1, code: 'x', letter_template: 2 } }),
        upload,
      ),
      { state: 'imported', imported: { letter_template: 2 } },
    );
    assert.deepEqual(await importBundle(async () => ({ ok: true, imported: null }), upload), {
      state: 'imported',
      imported: {},
    });
  });

  test('an answer after the page closes is dropped', async () => {
    const { rest } = backend();
    const section = pageWith(rest, await checkBundle(rest, bundleFile));
    section.onImport();
    runCleanups();
    await tick();
    assert.deepEqual(imports(), [{ state: 'importing' }]);
  });
});

describe('US-10.4 an invalid bundle is refused', () => {
  test('test_us_10_4_pane_invalid_bundle_refused', async () => {
    const { rest, requests } = backend({
      preview: {
        ok: true,
        valid: false,
        problem: 'invalid bundle at items.2.rule_card.source: missing',
      },
    });
    const refused = await checkBundle(rest, bundleFile);
    assert.deepEqual(refused, {
      state: 'invalid',
      problem: 'invalid bundle at items.2.rule_card.source: missing',
    });
    assert.equal(
      describeImport(refused),
      'This file is not a valid corpus bundle (invalid bundle at items.2.rule_card.source: ' +
        'missing); nothing was imported.',
    );
    const shown = CorpusImportSection({
      state: refused,
      onPick() {},
      onImport() {},
      onCancel() {},
    });
    assert.equal(shown.props.children[5], null, 'no import button for an invalid file');
    assert.ok(requests.every((r) => r.path === '/corpus/import/preview'));
  });

  test('a file over the limit is refused before it is read', async () => {
    let read = false;
    const big = {
      ...bundleFile,
      size: MAX_BUNDLE_BYTES + 1,
      arrayBuffer: async () => {
        read = true;
        return BYTES;
      },
    };
    const { rest, requests } = backend();
    assert.deepEqual(await checkBundle(rest, big), {
      state: 'invalid',
      problem: 'bundle is larger than 5 MiB',
    });
    assert.equal(read, false);
    assert.equal(requests.length, 0);
  });

  test('previews are read defensively', async () => {
    assert.equal(previewOf(null), null);
    assert.equal(previewOf({ ok: true }), null);
    assert.deepEqual(previewOf({ ok: true, valid: false, problem: 7 }), {
      valid: false,
      problem: 'invalid bundle',
    });
    assert.deepEqual(previewOf({ ok: true, valid: true, by_kind: null, payers: 'x' }), {
      valid: true,
      summary: {
        items: 0,
        byKind: {},
        payers: [],
        morePayers: 0,
        stale: 0,
        replaces: 0,
        replaced: [],
      },
    });
    const { size: _size, ...sizeless } = bundleFile; // a host that reports no size
    assert.equal((await checkBundle(backend().rest, sizeless)).state, 'preview');
    assert.deepEqual(await checkBundle(async () => ({ ok: false }), { ...bundleFile, type: '' }), {
      state: 'failed',
      code: null,
    });
    const down = await checkBundle(async () => {
      throw rejection(503, 'worker_unavailable');
    }, bundleFile);
    assert.deepEqual(down, { state: 'failed', code: 'worker_unavailable' });
    assert.match(describeImport({ state: 'checking' }), /Checking/);
    assert.equal(describeImport({ state: 'idle' }), '');
  });
});

describe('US-10.4 review regressions', () => {
  test('the replaced items are named, kind by kind', () => {
    const state = {
      state: 'preview',
      upload: {},
      summary: {
        items: 60,
        byKind: { code: 60 },
        payers: [],
        morePayers: 0,
        stale: 0,
        replaces: 3,
        replaced: ['code CARC/197', 'letter_template appeal-l1', 'mystery thing'],
      },
    };
    const shown = CorpusImportSection({ state, onPick() {}, onImport() {}, onCancel() {} });
    assert.equal(
      shown.props.children[5].props.children,
      'Replaces: code CARC/197, letter template appeal-l1, mystery thing.',
    );
    const capped = { ...state, summary: { ...state.summary, replaces: 55 } };
    const more = CorpusImportSection({ state: capped, onPick() {}, onImport() {}, onCancel() {} });
    assert.match(more.props.children[5].props.children, / and 52 more\.$/);
    assert.deepEqual(previewOf({ ...PREVIEW, replaced: ['x', 7] }).summary.replaced, ['x']);
  });

  test('picking the same file again is a change', () => {
    const picked = [];
    const shown = CorpusImportSection({
      state: { state: 'idle' },
      onPick: (files) => picked.push(files),
      onImport() {},
      onCancel() {},
    });
    const target = { files: [bundleFile], value: 'C:\\fakepath\\rules.yaml' };
    shown.props.children[2].props.onChange({ currentTarget: target });
    assert.equal(target.value, '', 'the input is cleared after each pick');
    assert.deepEqual(picked, [[bundleFile]]);
    shown.props.children[2].props.onChange({ currentTarget: { files: null, value: '' } });
    assert.deepEqual(picked[1], []);
  });

  test('a failed import keeps the file for Try again and refreshes the corpus', async () => {
    let fail = true;
    const { rest, requests } = backend({
      fail: (path) =>
        fail && path === '/corpus/import?confirm=true' ? rejection(503, 'model_busy') : null,
    });
    const previewedState = await checkBundle(rest, bundleFile);
    pageWith(rest, previewedState).onImport();
    await tick();
    const failed = imports().at(-1);
    assert.deepEqual(failed, {
      state: 'failed',
      code: 'model_busy',
      upload: previewedState.upload,
    });
    await tick();
    assert.equal(hooks.states[slot.corpus].updates.at(-1).state, 'ok', 'checked after a failure');

    const shown = CorpusImportSection({ state: failed, onPick() {}, onImport() {}, onCancel() {} });
    assert.equal(shown.props.children[8].props.children, 'Try again');
    fail = false;
    pageWith(rest, failed).onImport();
    await tick();
    assert.equal(imports().at(-1).state, 'imported');
    const confirmed = requests.filter((r) => r.path === '/corpus/import?confirm=true');
    assert.equal(confirmed.length, 2);
    assert.equal(confirmed[1].opts.upload, previewedState.upload, 'the same bytes, not a re-pick');
  });

  test('a failed preview offers no Try again', () => {
    const shown = CorpusImportSection({
      state: { state: 'failed', code: 'worker_unavailable' },
      onPick() {},
      onImport() {},
      onCancel() {},
    });
    assert.equal(shown.props.children[8], null);
    const { rest } = backend();
    pageWith(rest, { state: 'failed', code: 'worker_unavailable' }).onImport();
    assert.deepEqual(imports(), []);
  });

  test('the pane waits longer than the gateway', () => {
    assert.ok(IMPORT_TIMEOUT_MS > 900_000);
  });
});
