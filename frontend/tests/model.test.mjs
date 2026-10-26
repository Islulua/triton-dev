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

test('timeline zoom preserves the pointer time and shortcuts leave browser modifiers alone', async () => {
  const { anchoredTimelineScroll, timelineShortcut } = await import('../src/timeline-navigation.js');
  const next = anchoredTimelineScroll(1000, 2000, 200, 400);
  assert.ok(Math.abs((200 + 400 - 190) / 798 - (next + 400 - 190) / 1798) < 1e-10);
  assert.equal(anchoredTimelineScroll(1000, 1000, 200, 400), 200);
  assert.equal(timelineShortcut({ key: 'W' }), 'in');
  assert.equal(timelineShortcut({ key: 'ArrowRight' }), 'right');
  assert.equal(timelineShortcut({ key: '+', metaKey: true }), null);
  assert.equal(timelineShortcut({ key: 'a', ctrlKey: true }), null);
});

test('run statistics count configurations once and keep skips/incomplete outside pass-rate denominator', async () => {
  const { buildRunStatistics, filterStatisticRows } = await import('../src/run-statistics.js');
  const outcomes = [...Array(22).fill('passed'), ...Array(3).fill('failed'), 'skipped', 'skipped', 'xfailed', 'xpassed', 'incomplete', 'incomplete', 'incomplete'];
  const rows = outcomes.map((outcome, i) => ({ nodeid: `test_ops.py::test_op[${i}]`, outcome, duration: i / 100 + .1, stages: [{ when: i === 22 ? 'setup' : 'call', outcome: outcome === 'failed' ? 'failed' : 'passed', duration: .1 }] }));
  rows[22].stages.push({ when: 'teardown', outcome: 'failed', duration: .01 });
  const collection = rows.map((r, i) => ({ nodeid: r.nodeid, operator: i < 24 ? 'matmul' : 'softmax', logical_nodeid: i < 24 ? 'test_matmul' : 'test_softmax' }));
  const run = { state: 'cancelled', started_at: 10, finished_at: 12, request: { nodeids: rows.map(r => r.nodeid) }, test_results: [...rows, rows[0]], summary: { passed: 999 } };
  const stats = buildRunStatistics(run, collection);
  assert.equal(stats.total, 32); assert.equal(stats.counts.passed, 22); assert.equal(stats.counts.failed, 3);
  assert.equal(stats.passRate, 22 / 25); assert.equal(stats.coverage, 29 / 32);
  assert.equal(stats.operatorCount, 2); assert.equal(stats.logicalCount, 2);
  assert.equal(stats.phases.find(p => p.phase === 'setup').count, 1);
  assert.equal(stats.phases.find(p => p.phase === 'teardown').count, 1);
  assert.equal(stats.phases.find(p => p.phase === 'call').count, 2);
  assert.equal(stats.elapsed, 2); assert.ok(stats.cumulativeDuration > stats.elapsed);
  assert.equal(stats.measuredCount, 29); assert.equal(stats.slowest.length, 10);
  assert.equal(filterStatisticRows(stats, { operator: 'matmul', status: 'failed' }).length, 2);
  assert.equal(filterStatisticRows(stats, { phase: 'teardown' })[0].nodeid, rows[22].nodeid);
});

test('statistics do not invent operator names, completion or timings from missing reports', async () => {
  const { buildRunStatistics } = await import('../src/run-statistics.js');
  const pending = buildRunStatistics({ state: 'running', request: { nodeids: ['test_ops.py::test_matmul[0]'] } });
  assert.equal(pending.counts.pending, 1); assert.equal(pending.passRate, null); assert.equal(pending.measuredCount, 0);
  assert.equal(pending.rows[0].operator, '未标注算子'); assert.equal(pending.operatorCount, 0);
  const cancelled = buildRunStatistics({ state: 'cancelled', request: { nodeids: ['test_ops.py::test_matmul[0]'] } });
  assert.equal(cancelled.counts.incomplete, 1); assert.equal(cancelled.coverage, 0);
  const conflict = buildRunStatistics({ state: 'passed', test_results: [{ nodeid: 'x', outcome: 'passed', duration: 5, stages: [{ context: { operator: 'matmul' }, properties: [['operator', 'add']] }] }] });
  assert.equal(conflict.rows[0].operator, '元数据冲突'); assert.equal(conflict.operatorCount, 0);
});

test('rerun comparison retains omitted parent configurations and does not call new cases regressions', async () => {
  const { buildRunStatistics, filterStatisticRows } = await import('../src/run-statistics.js');
  const make = (entries, extra = {}) => ({ state: 'failed', request: { nodeids: entries.map(([nodeid]) => nodeid) }, test_results: entries.map(([nodeid, outcome]) => ({ nodeid, outcome })), ...extra });
  const parent = make([['a', 'passed'], ['b', 'failed'], ['c', 'failed'], ['d', 'skipped']], { runtime: { python: '3.10' }, source_snapshot: { sha256: 'same' } });
  const child = make([['a', 'failed'], ['b', 'passed'], ['c', 'failed'], ['new', 'failed']], { parent: 'parent-id', runtime: { python: '3.12' }, source_snapshot: { sha256: 'same' } });
  const stats = buildRunStatistics(child, [], parent);
  assert.equal(stats.changeCounts.new_failure, 1); assert.equal(stats.changeCounts.recovered, 1);
  assert.equal(stats.changeCounts.persistent_failure, 1); assert.equal(stats.changeCounts.not_covered, 1);
  assert.equal(stats.changeCounts.no_baseline, 1); assert.equal(stats.changes.find(c => c.nodeid === 'd').selected, false);
  assert.equal(stats.sameSource, true); assert.equal(stats.sameEnvironment, false);
  assert.equal(filterStatisticRows(stats, { change: 'recovered' })[0].nodeid, 'b');
  assert.equal(filterStatisticRows(stats, { change: 'not_covered' }).length, 0);
});

test('browser demo statistics preserve mock source and do not fabricate per-case timings', async () => {
  const { demoStatisticsRecord, buildRunStatistics } = await import('../src/run-statistics.js');
  const cases = [{ id: 'a', name: 'test_a[x]' }, { id: 'b', name: 'test_b[x]' }];
  const run = { id: 'demo', caseIds: ['a', 'b'], failedIds: ['b'], state: 'failed' };
  const record = demoStatisticsRecord(run, cases), stats = buildRunStatistics(record);
  assert.equal(record.source, 'browser-demo'); assert.equal(stats.counts.passed, 1); assert.equal(stats.counts.failed, 1);
  assert.equal(stats.elapsed, null); assert.equal(stats.measuredCount, 0);
  assert.equal(buildRunStatistics(demoStatisticsRecord({ ...run, state: 'cancelled' }, cases)).counts.incomplete, 2);
});

test('case reports group by file and class/function identity then preserve individual configurations', async () => {
  const { buildTestReport, filterReportRows } = await import('../src/test-report.js');
  const ids = ['math.py::TestA::test_op[x]', 'math.py::TestA::test_op[y]', 'math.py::TestB::test_op[x]', 'memory.py::test_copy[z]'];
  const collection = ids.map((nodeid, i) => ({ nodeid, logical_nodeid: nodeid.slice(0, nodeid.indexOf('[')), parameter_id: ['x', 'y', 'x', 'z'][i], parameters: { dtype: 'fp16' }, case_id: 'same-business-id', operator: 'matmul' }));
  const run = { state: 'failed', request: { nodeids: [...ids, ids[0]] }, test_results: ids.map((nodeid, i) => ({ nodeid, outcome: i === 1 ? 'failed' : 'passed', duration: .12, stages: [{ when: 'call', outcome: i === 1 ? 'failed' : 'passed', duration: .12, time: 101, worker_id: 'gw0', pid: 12 }] })), stages: [{ type: 'test_started', nodeid: ids[0], time: 100, worker_id: 'gw0', pid: 12 }] };
  const report = buildTestReport(run, collection);
  assert.equal(report.total, 4); assert.equal(report.files.length, 2); assert.equal(report.files[0].cases.length, 2);
  assert.equal(report.files[0].cases[0].rows.length, 2); assert.equal(report.rows[0].parameter, 'x');
  assert.equal(report.counts.PASS, 3); assert.equal(report.counts.FAIL, 1);
  assert.equal(report.rows[0].startedAt, 100); assert.equal(report.rows[0].endedAt, 101);
  assert.equal(report.rows[1].startedAt, null); assert.equal(report.rows[0].duration, .12);
  assert.equal(filterReportRows(report.rows, 'dtype', 'FAIL').length, 1);
});

test('CRASH attribution requires a started active case, abnormal worker exit and no teardown', async () => {
  const { buildTestReport } = await import('../src/test-report.js');
  const record = { state: 'failed', request: { nodeids: ['f.py::test_old', 'f.py::test_crash', 'f.py::test_unstarted'] },
    test_results: [{ nodeid: 'f.py::test_old', outcome: 'passed', duration: .1, stages: [{ when: 'teardown', outcome: 'passed', time: 11 }] }, { nodeid: 'f.py::test_crash', outcome: 'incomplete', stages: [{ when: 'setup', outcome: 'passed', time: 13 }] }],
    stages: [{ type: 'test_started', nodeid: 'f.py::test_old', worker_id: 'gw0', time: 10 }, { type: 'stage', nodeid: 'f.py::test_old', worker_id: 'gw0', when: 'teardown', time: 11 }, { type: 'test_started', nodeid: 'f.py::test_crash', worker_id: 'gw0', time: 12 }, { type: 'worker_exit', target_worker_id: 'gw0', time: 14, error: 'worker exited unexpectedly' }] };
  const report = buildTestReport(record);
  assert.deepEqual(report.rows.map(r => r.status), ['PASS', 'CRASH', 'INCOMPLETE']);
  assert.equal(report.rows[1].outcome, 'incomplete'); assert.equal(report.rows[1].endedAt, 14);
  const noStart = buildTestReport({ ...record, stages: record.stages.filter(e => e.type !== 'test_started') });
  assert.equal(noStart.counts.CRASH, 0);
});

test('cancelled and timed-out runs do not turn worker shutdown into a case crash', async () => {
  const { buildTestReport } = await import('../src/test-report.js');
  const base = { request: { nodeids: ['f.py::test_active', 'f.py::test_not_run'] }, stages: [{ type: 'test_started', worker_id: 'gw0', nodeid: 'f.py::test_active', time: 10 }, { type: 'worker_exit', target_worker_id: 'gw0', error: 'killed', time: 12 }] };
  assert.deepEqual(buildTestReport({ ...base, state: 'cancelled' }).rows.map(r => r.status), ['CANCELLED', 'INCOMPLETE']);
  assert.deepEqual(buildTestReport({ ...base, state: 'timeout' }).rows.map(r => r.status), ['TIMEOUT', 'INCOMPLETE']);
});

test('portable test reports escape names and evidence and keep PASS/FAIL colour labels', async () => {
  const { testReportHtml, buildTestReport } = await import('../src/test-report.js');
  const record = { id: '<script>report</script>', state: 'failed', source: 'browser-demo', test_results: [{ nodeid: 'test_x[<img src=x onerror=alert(1)>]', outcome: 'failed', stages: [{ when: 'call', outcome: 'failed', longrepr: '<script>alert(1)</script>' }] }] };
  const html = testReportHtml(record);
  assert.ok(html.includes('class="badge FAIL"')); assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>') && !html.includes('<img'));
  assert.equal(buildTestReport(record).files[0].name, '未记录文件');
  assert.equal(buildTestReport(record).rows[0].startedAt, null);
  assert.equal(buildTestReport(record).rows[0].duration, null);
});
