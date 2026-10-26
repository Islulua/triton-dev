import test from 'node:test';
import assert from 'node:assert/strict';
import { freshState, loadState, validateCombination, combinationDiff, demoFailure, validateParams, normalizeTask } from '../src/model.js';

test('immutable names and sources are checked before saving a combination', () => {
  const state = freshState();
  assert.match(validateCombination({ name: 'baseline', sdk: '1022', triton: '1022', torch: '1022' }, state.environments), /已存在/);
  assert.match(validateCombination({ name: '../escape', sdk: '1022', triton: '1022', torch: '1022' }, []), /名称/);
  assert.match(validateCombination({ name: 'new', sdk: 'missing', triton: '1022', torch: '1022' }, []), /制品/);
  assert.equal(validateCombination({ name: 'new', sdk: '1022', triton: '1023', torch: '1022' }, state.environments), '');
  assert.deepEqual(combinationDiff(state.environments[0], state.environments[2]).filter(x => x.changed).map(x => x.field), ['Triton wheel']);
});
test('mock result is deterministic and requires explicit parameter changes', () => {
  assert.deepEqual(demoFailure(['matmul'], { M: 128 }), ['matmul']);
  assert.deepEqual(demoFailure(['matmul'], { M: 128 }), ['matmul']);
  assert.deepEqual(demoFailure(['matmul'], { M: 64 }), []);
  assert.match(validateParams({ M: 'not-number', N: 1 }), /整数/);
  assert.equal(validateParams({ M: 128, N: 128 }), '');
});
test('reload does not leave old mock jobs permanently running', () => {
  const state = freshState(); state.runs[0].state = 'running'; state.environments[0].status = 'preparing';
  const loaded = loadState({ getItem: () => JSON.stringify(state) });
  assert.equal(loaded.runs[0].state, 'interrupted');
  assert.equal(loaded.environments[0].status, 'unverified');
  assert.equal(loadState({ getItem: () => '{broken' }).runs[0].state, 'failed');
});
test('local API tasks do not invent kernel stages or test results', () => {
  const task = normalizeTask({ id: 'run_real', state: 'failed', request: { argv: ['python', 'reproduce.py'] }, result: { returncode: 7 } });
  assert.equal(task.source, 'api'); assert.deepEqual(task.caseIds, []); assert.deepEqual(task.failedIds, []);
  assert.equal(task.record.result.returncode, 7);
});

test('32 configurations group by function while selecting exactly one nodeid', async () => {
  const { groupCases, selectConfigurations } = await import('../src/pytest-model.js');
  const items = Array.from({ length: 32 }, (_, n) => ({ nodeid: `test_matrix.py::test_shape[${n}]`, logical_nodeid: 'test_matrix.py::test_shape', parameters: { n }, markers: ['parametrize'] }));
  const groups = groupCases(items);
  assert.equal(groups.length, 1); assert.equal(groups[0].cases.length, 32);
  let selected = selectConfigurations([], [items[17].nodeid], true);
  assert.deepEqual(selected, ['test_matrix.py::test_shape[17]']);
  selected = selectConfigurations(selected, items.slice(0, 2).map(c => c.nodeid), true);
  assert.equal(selected.length, 3);
  assert.deepEqual(selectConfigurations(selected, items.slice(0, 2).map(c => c.nodeid), false), ['test_matrix.py::test_shape[17]']);
  const legacy = groupCases([{ nodeid: 'test_file.py::ClassA::test_shape[x]', case_id: 'same' }, { nodeid: 'test_file.py::ClassB::test_shape[x]', case_id: 'same' }]);
  assert.equal(legacy.length, 2);
});
