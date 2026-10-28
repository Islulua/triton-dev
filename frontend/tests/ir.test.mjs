import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeIRDocument, linkedLines, acceptCompileResult, parseTraceText, sameSource, needsCompilation } from '../src/ir-model.js';

const fixture = {
  schema_version: 1, source_kind: 'imported', kernel: 'add', source_hash: 'hash-one',
  source: { code: 'def add(x):\n    return x + 1', file_path: '/a/kernel.py', start_line: 10 },
  stages: [{ id: 'ttir', label: 'TTIR', content: 'add\nreturn', mapping: {
    1: { file: '/a/kernel.py', line: 11, column: 4 },
    2: { file: '/b/kernel.py', line: 11, column: 4 },
    999: { file: '/a/kernel.py', line: 11, column: 4 },
  } }],
};

test('source selection highlights only exact file matches inside the current IR document', () => {
  const doc = normalizeIRDocument(fixture);
  assert.deepEqual(linkedLines(doc, 'ttir', { file: '/a/kernel.py', line: 11 }), [1]);
  assert.deepEqual(linkedLines(doc, 'ttir', { file: '/a/kernel.py', line: 99 }), []);
});
test('edits and out-of-order compilation cannot attach an old result to a new source', () => {
  assert.equal(acceptCompileResult({ revision: 3, request: 2 }, { revision: 2, request: 2 }), false);
  assert.equal(acceptCompileResult({ revision: 3, request: 3 }, { revision: 3, request: 2 }), false);
  assert.equal(acceptCompileResult({ revision: 3, request: 3 }, { revision: 3, request: 3 }), true);
});
test('trace import keeps separate kernel specializations and stage mappings', () => {
  const entry = hash => ({ event_type: 'compilation', metadata: { name: 'add', hash }, payload: {
    python_source: fixture.source, file_content: { 'add.ttir': 'add\nreturn' },
    source_mappings: { ttir: { 1: { file: '/a/kernel.py', line: 11 } } },
  } });
  const docs = parseTraceText([entry('first'), entry('second')].map(JSON.stringify).join('\n'));
  assert.equal(docs.length, 2);
  assert.deepEqual(docs.map(d => d.metadata.hash), ['first', 'second']);
  assert.deepEqual(linkedLines(docs[1], 'ttir', { file: '/a/kernel.py', line: 11 }), [1]);
});
test('normalized export roundtrips and malformed stage collections fail clearly', () => {
  assert.equal(parseTraceText(JSON.stringify(fixture))[0].kernel, 'add');
  assert.throws(() => parseTraceText('{broken'), /JSON|格式/);
  assert.throws(() => normalizeIRDocument({ ...fixture, stages: [] }), /IR/);
});
test('offline imports validate display types and never authenticate compiled provenance', () => {
  assert.throws(() => normalizeIRDocument({ ...fixture, source: { ...fixture.source, file_path: {} } }), /路径|源码/);
  const doc = parseTraceText(JSON.stringify({ ...fixture, source_kind: 'compiled', kernel: { forged: true } }));
  assert.equal(doc[0].source_kind, 'imported');
  assert.equal(doc[0].kernel, 'kernel');
  const malformed = normalizeIRDocument({ ...fixture, metadata: { hash: 123, backend: {}, name: [] }, stages: [{ ...fixture.stages[0], label: {} }] });
  assert.equal(malformed.metadata.hash, undefined);
  assert.equal(malformed.stages[0].label, 'TTIR');
});
test('matching text alone never links a different file or extracted source range', () => {
  assert.equal(sameSource(fixture.source, { ...fixture.source, file_path: '/b/kernel.py' }), false);
  assert.equal(sameSource(fixture.source, { ...fixture.source, start_line: 11 }), false);
  assert.equal(sameSource(fixture.source, { ...fixture.source }), true);
});
test('configuration-only edits require a new compilation', () => {
  const current = { code: 'kernel', spec: '{"N":32}', entry: 'add', compiler: 'sdk' };
  assert.equal(needsCompilation(current, current), false);
  assert.equal(needsCompilation({ ...current, spec: '{"N":64}' }, current), true);
  assert.equal(needsCompilation({ ...current, compiler: 'sdk-next' }, current), true);
});
