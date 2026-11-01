/**
 * node --test suite for case intake in the pane. US-5.1 scenarios:
 *   - A PDF or image is attached to a new case
 *   - Pasted 835 text is attached to a case
 */
import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import plugin, {
  addFile,
  addFiles,
  addText,
  CasePane,
  createCaseApi,
  DocumentList,
  describeCase,
  documentsOf,
  MAX_FILE_BYTES,
  REFUSALS,
  refusalOf,
} from '../plugin.js';
import { byArea, casePaneOf, createFakeCtx } from './fake_ctx.mjs';
import { hostAccesses } from './fakes/plugin-sdk.mjs';
import { hooks, resetHooks, runCleanups } from './fakes/react.mjs';

const tick = () => new Promise((resolve) => setImmediate(resolve));
const ERA = 'ISA*00*...~ST*835*0001~CLP*PCN-0001*4*250*0~SE*3*0001~';
const pdf = {
  name: 'Doe_Jane_EOB.pdf',
  type: 'application/pdf',
  arrayBuffer: async () => new TextEncoder().encode('%PDF-1.7 synthetic').buffer,
};
const png = { ...pdf, name: 'scan.png', type: 'image/png' };

/** Pane children, by role. */
const at = {
  input: 2,
  status: 3,
  process: 4,
  newCase: 5,
  paste: 6,
  attach: 7,
  list: 8,
  refresh: 9,
  fields: 10,
};

/** A worker that keeps documents per case, as plugin_api does. */
function caseBackend() {
  const cases = new Map();
  let next = 1;
  const rest = async (path, opts) => {
    if (path === '/health') return { ok: true, status: 'ok', version: '0.1.0' };
    if (path === '/cases' && opts?.method === 'POST') {
      const caseId = `case_${String(next++).padStart(16, '0')}`;
      cases.set(caseId, []);
      return { ok: true, case_id: caseId, documents: [] };
    }
    const match = path.match(/^\/cases\/([^/]+)(?:\/(documents|paste))?$/);
    const docs = cases.get(match?.[1]);
    if (!docs) throw new Error('404: {"ok":false,"error":{"code":"case_not_found","message":"x"}}');
    if (match[2] === 'documents') {
      const kind = opts.upload.contentType.startsWith('image/') ? 'image' : 'pdf';
      docs.push({ doc_id: `src_${docs.length}`, kind, filename: opts.upload.filename });
    } else if (match[2] === 'paste') {
      const kind = opts.body.text.startsWith('ISA') ? 'edi_835' : 'text';
      docs.push({ doc_id: `src_${docs.length}`, kind, filename: null });
    }
    return { ok: true, case_id: match[1], documents: docs };
  };
  return { rest, cases };
}

/** Render the registered pane (the one `register` contributes). */
function renderPane(ctx) {
  const element = casePaneOf(byArea(ctx.recorded).panes[0].render());
  return { element, pane: element.type(element.props) };
}

/** Re-render the pane from the state it ended in, as React would. */
function rerender(element, ...seed) {
  resetHooks();
  hooks.seed = seed;
  return element.type(element.props);
}

const drop = (...files) => ({ preventDefault() {}, dataTransfer: { files } });

/** The pane's `life` slot as it is once the pane has worked on `caseId`. */
const life = (caseId = null) => ({
  live: true,
  action: 0,
  caseId,
  processing: null,
  onProgress() {},
});

afterEach(runCleanups);

beforeEach(() => {
  resetHooks();
  hostAccesses.length = 0;
});

describe('US-5.1 a PDF or image is attached to a new case', () => {
  test('test_us_5_1_pane_drop_attaches_pdf_or_image_to_new_case', async () => {
    const { rest } = caseBackend();
    const ctx = createFakeCtx({ rest });
    plugin.register(ctx);
    const { element, pane } = renderPane(ctx);
    let prevented = 0;
    pane.props.onDragOver({ preventDefault: () => prevented++ });
    pane.props.onDrop({ ...drop(pdf), preventDefault: () => prevented++ });
    await tick();
    const ready = hooks.states[0].updates.at(-1);
    assert.equal(prevented, 2, 'the webview never opens the dropped file');
    assert.deepEqual(ready, {
      state: 'ready',
      caseId: 'case_0000000000000001',
      documents: [{ docId: 'src_0', kind: 'pdf', label: 'Doe_Jane_EOB.pdf' }],
      fields: [],
    });
    assert.deepEqual(
      ctx.recorded.restRequests.map((r) => [r.method, r.path]),
      [
        ['POST', '/cases'],
        ['POST', '/cases/case_0000000000000001/documents'],
        ['GET', '/cases/case_0000000000000001'],
      ],
    );

    const shown = rerender(element, ready);
    const list = shown.props.children[at.list];
    assert.equal(list.props['aria-label'], 'Source documents');
    assert.deepEqual(
      list.props.children.map((li) => [li.props['data-kind'], li.props.children]),
      [['pdf', 'Doe_Jane_EOB.pdf']],
    );
    assert.match(shown.props.children[at.status].props.children, /ready to process/);
    assert.deepEqual(hostAccesses, [], 'case intake never touches host (BR-2)');
  });

  test('test_us_5_1_pane_drop_adds_to_the_open_case', async () => {
    const { rest, cases } = caseBackend();
    const api = createCaseApi(rest);
    const first = await addFile(api, null, pdf);
    const pane = rerender({ type: CasePane, props: { rest } }, first, life(first.caseId));
    pane.props.onDrop(drop(png));
    await tick();
    const ready = hooks.states[0].updates.at(-1);
    assert.equal(ready.caseId, first.caseId, 'no second case');
    assert.deepEqual(
      ready.documents.map((d) => d.kind),
      ['pdf', 'image'],
    );
    assert.equal(cases.size, 1);
  });

  test('a refused upload keeps the case open and explains the refusal with fixed text', async () => {
    const backend = caseBackend();
    const leaked = 'Jane Doe is not allowed';
    const rest = async (path, opts) => {
      if (path.endsWith('/documents')) {
        throw new Error(
          `415: {"ok":false,"error":{"code":"unsupported_document","message":"${leaked}"}}`,
        );
      }
      return backend.rest(path, opts);
    };
    const state = await addFile(createCaseApi(rest), null, pdf);
    assert.deepEqual(state, {
      state: 'ready',
      caseId: 'case_0000000000000001',
      documents: [],
      fields: [],
      notice: 'unsupported_document',
    });
    const text = describeCase(state);
    assert.ok(text.startsWith(REFUSALS.unsupported_document));
    assert.doesNotMatch(text, /Jane Doe/);
  });

  test('a refusal whose case cannot be reopened, or an unknown code, reads as unavailable', async () => {
    const tooLarge = new Error('413: {"ok":false,"error":{"code":"document_too_large"}}');
    let reads = 0;
    const gone = createCaseApi(async (path) => {
      if (path === '/cases') return { ok: true, case_id: 'case_1' };
      if (path.endsWith('/documents')) throw tooLarge;
      reads += 1;
      throw new Error('503');
    });
    assert.deepEqual(await addFile(gone, null, pdf), { state: 'unavailable' });
    assert.equal(reads, 1);
    const failing = createCaseApi(async () => {
      throw new Error('502: {"ok":false,"error":{"code":"worker_error"}}');
    });
    assert.deepEqual(await addFile(failing, 'case_1', pdf), {
      state: 'unavailable',
      caseId: 'case_1',
    });
    assert.deepEqual(await addFile(failing, null, pdf), { state: 'unavailable' });
    const odd = createCaseApi(async () => ({ ok: true, case_id: 'not a case id' }));
    assert.deepEqual(await addText(odd, null, ERA), { state: 'unavailable' });
  });

  test('refusalOf reads only known codes from a Hermes rejection', () => {
    assert.equal(refusalOf(new Error('409: {"error":{"code":"case_closed"}}')), 'case_closed');
    assert.equal(refusalOf(new Error('500: {"error":{"code":"internal_error"}}')), null);
    assert.equal(refusalOf(new Error('500: {"error":{"code":42}}')), null);
    assert.equal(refusalOf(new Error('500: {not json')), null);
    assert.equal(refusalOf(new Error('Hermes desktop bridge unavailable')), null);
    assert.equal(refusalOf('413: {"error":{"code":"document_too_large"}}'), null);
    assert.equal(refusalOf(new Error('500: null')), null);
  });
});

describe('US-5.1 pasted 835 text is attached to a case', () => {
  test('test_us_5_1_pane_pasted_835_attached', async () => {
    const { rest } = caseBackend();
    const ctx = createFakeCtx({ rest });
    const api = createCaseApi((path, opts) => ctx.rest(path, opts));
    const open = await addFile(api, null, pdf);
    const element = { type: CasePane, props: { rest: (path, opts) => ctx.rest(path, opts) } };

    // The biller types into the paste box, React re-renders with the draft, then Attach.
    const typing = rerender(element, open);
    typing.props.children[at.paste].props.onChange({ currentTarget: { value: ERA } });
    assert.deepEqual(hooks.states[2].updates, [ERA]);
    const pane = rerender(element, open, life(open.caseId), ERA);
    assert.equal(pane.props.children[at.attach].props.disabled, false);
    pane.props.children[at.attach].props.onClick();
    await tick();
    assert.deepEqual(hooks.states[2].updates, [''], 'the paste box clears');
    const ready = hooks.states[0].updates.at(-1);
    assert.deepEqual(ready.documents.at(-1), {
      docId: 'src_1',
      kind: 'edi_835',
      label: 'Pasted 835 text',
    });
    const paste = ctx.recorded.restRequests.find((r) => r.path.endsWith('/paste'));
    assert.deepEqual(paste, {
      path: `/cases/${open.caseId}/paste`,
      method: 'POST',
      opts: { method: 'POST', body: { text: ERA } },
    });
  });

  test('pasting with no case open creates one; a blank draft sends nothing', async () => {
    const { rest, cases } = caseBackend();
    const state = await addText(createCaseApi(rest), null, 'Denial letter: CO-197');
    assert.equal(state.state, 'ready');
    assert.deepEqual(state.documents, [{ docId: 'src_0', kind: 'text', label: 'Pasted text' }]);
    assert.equal(cases.size, 1);

    const calls = [];
    const pane = rerender(
      { type: CasePane, props: { rest: async (p) => calls.push(p) } },
      {
        state: 'idle',
      },
      life(),
      '   ',
    );
    assert.equal(pane.props.children[at.attach].props.disabled, true);
    pane.props.children[at.attach].props.onClick();
    const busy = rerender(
      { type: CasePane, props: { rest: async (p) => calls.push(p) } },
      {
        state: 'busy',
      },
      life(),
      ERA,
    );
    busy.props.children[at.attach].props.onClick();
    await tick();
    assert.deepEqual(calls, []);
  });
});

describe('case pane controls', () => {
  test('New case returns to the drop prompt and drops a late answer', async () => {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const { rest } = caseBackend();
    const slow = async (path, opts) => {
      await gate;
      return rest(path, opts);
    };
    const element = { type: CasePane, props: { rest: slow } };
    const idle = rerender(element);
    assert.equal(idle.props.children[at.newCase].props.disabled, true);
    const ready = { state: 'ready', caseId: 'case_1', documents: [] };
    const pane = rerender(element, ready);
    assert.equal(pane.props.children[at.newCase].props.disabled, false);
    pane.props.onDrop({ preventDefault() {}, dataTransfer: { files: [pdf] } });
    pane.props.children[at.newCase].props.onClick();
    release();
    await tick();
    await tick();
    assert.deepEqual(hooks.states[0].updates, [{ state: 'busy' }, { state: 'idle' }]);
  });

  test('a drop without files, or while busy, does nothing', async () => {
    const calls = [];
    const element = { type: CasePane, props: { rest: async (p) => calls.push(p) } };
    const pane = rerender(element);
    pane.props.onDrop({ preventDefault() {}, dataTransfer: null });
    pane.props.onDrop({ preventDefault() {}, dataTransfer: { files: [] } });
    const busy = rerender(element, { state: 'busy' });
    busy.props.onDrop(drop(pdf));
    await tick();
    assert.deepEqual(calls, []);
  });

  test('documentsOf keeps only well-formed entries', () => {
    assert.deepEqual(documentsOf(null), []);
    assert.deepEqual(documentsOf({ documents: 'x' }), []);
    assert.deepEqual(
      documentsOf({
        documents: [
          null,
          { doc_id: 1, kind: 'pdf' },
          { doc_id: 'a', kind: 7 },
          { doc_id: 'b', kind: 'image', filename: 'scan.png' },
          { doc_id: 'c', kind: 'text', filename: null },
        ],
      }),
      [
        { docId: 'b', kind: 'image', label: 'scan.png' },
        { docId: 'c', kind: 'text', label: 'Pasted text' },
      ],
    );
  });

  test('DocumentList renders one item per document', () => {
    const list = DocumentList([{ docId: 'a', kind: 'pdf', label: 'eob.pdf' }]);
    assert.equal(list.type, 'ul');
    assert.equal(list.props.children[0].props.children, 'eob.pdf');
  });
});

describe('US-5.1 review regressions', () => {
  test('a case whose reopen fails stays the open case for the next drop', async () => {
    const { rest, cases } = caseBackend();
    let failReads = true;
    const flaky = async (path, opts) => {
      if (failReads && opts === undefined && path.startsWith('/cases/')) throw new Error('504');
      return rest(path, opts);
    };
    const element = { type: CasePane, props: { rest: flaky } };
    const pane = rerender(element);
    pane.props.onDrop(drop(pdf));
    await tick();
    const lost = hooks.states[0].updates.at(-1);
    const remembered = hooks.states[1].value;
    assert.deepEqual(lost, { state: 'unavailable', caseId: 'case_0000000000000001' });
    assert.equal(remembered.caseId, 'case_0000000000000001');

    failReads = false;
    const again = rerender(element, lost, remembered);
    assert.equal(again.props.children[at.refresh].props.disabled, false);
    again.props.onDrop(drop(png));
    await tick();
    assert.equal(cases.size, 1, 'the letter joins the first case');
    assert.deepEqual(
      hooks.states[0].updates.at(-1).documents.map((d) => d.kind),
      ['pdf', 'image'],
    );
  });

  test('two files dropped together go into one case, in order', async () => {
    const { rest, cases } = caseBackend();
    const state = await addFiles(createCaseApi(rest), null, [pdf, png]);
    assert.deepEqual(
      state.documents.map((d) => d.label),
      ['Doe_Jane_EOB.pdf', 'scan.png'],
    );
    assert.equal(cases.size, 1);
  });

  test('a refused file stops the rest of a multi-file drop', async () => {
    const backend = caseBackend();
    const sent = [];
    const rest = async (path, opts) => {
      if (path.endsWith('/documents')) {
        sent.push(opts.upload.filename);
        if (opts.upload.filename === 'scan.png') {
          throw new Error('415: {"ok":false,"error":{"code":"unsupported_document"}}');
        }
      }
      return backend.rest(path, opts);
    };
    const third = { ...pdf, name: 'letter.pdf' };
    const state = await addFiles(createCaseApi(rest), null, [pdf, png, third]);
    assert.equal(state.notice, 'unsupported_document');
    assert.deepEqual(sent, ['Doe_Jane_EOB.pdf', 'scan.png']);
    assert.deepEqual(await addFiles(createCaseApi(rest), null, []), { state: 'idle' });
  });

  test('a file over 16 MiB is refused before it is read', async () => {
    let reads = 0;
    const huge = { ...pdf, size: MAX_FILE_BYTES + 1, arrayBuffer: async () => reads++ };
    const { rest } = caseBackend();
    const api = createCaseApi(rest);
    const idle = await addFile(api, null, huge);
    assert.deepEqual(idle, { state: 'idle', notice: 'document_too_large' });
    assert.ok(describeCase(idle).startsWith(REFUSALS.document_too_large));
    const open = await addFile(api, null, pdf);
    const kept = await addFile(api, open.caseId, huge);
    assert.equal(kept.notice, 'document_too_large');
    assert.equal(kept.documents.length, 1);
    assert.equal(reads, 0);
  });

  test('a paste that is not attached goes back into the box', async () => {
    const rest = async (path) => {
      if (path === '/cases') return { ok: true, case_id: 'case_1' };
      if (path.endsWith('/paste')) {
        throw new Error('413: {"ok":false,"error":{"code":"document_too_large"}}');
      }
      return { ok: true, case_id: 'case_1', documents: [] };
    };
    const element = { type: CasePane, props: { rest } };
    const ready = { state: 'ready', caseId: 'case_1', documents: [], fields: [] };
    const pane = rerender(element, ready, life('case_1'), ERA);
    pane.props.children[at.attach].props.onClick();
    await tick();
    await tick();
    assert.deepEqual(hooks.states[2].updates, ['', ERA]);
    assert.equal(hooks.states[0].updates.at(-1).notice, 'document_too_large');
  });

  test('Refresh reopens the remembered case and is off without one', async () => {
    const { rest } = caseBackend();
    const api = createCaseApi(rest);
    const open = await addFile(api, null, pdf);
    const calls = [];
    const element = {
      type: CasePane,
      props: {
        rest: (path, opts) => {
          calls.push(path);
          return rest(path, opts);
        },
      },
    };
    const none = rerender(element);
    assert.equal(none.props.children[at.refresh].props.disabled, true);
    none.props.children[at.refresh].props.onClick();
    const busy = rerender(element, { state: 'busy' }, life(open.caseId));
    assert.equal(busy.props.children[at.refresh].props.disabled, true);
    busy.props.children[at.refresh].props.onClick();
    const pane = rerender(element, { state: 'unavailable' }, life(open.caseId));
    pane.props.children[at.refresh].props.onClick();
    await tick();
    assert.equal(calls.filter((p) => p.startsWith('/cases/')).length, 1);
    assert.equal(hooks.states[0].updates.at(-1).caseId, open.caseId);
  });
});
