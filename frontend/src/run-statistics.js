export const RESULT_NAMES = { passed: '通过', failed: '失败', skipped: '跳过', xfailed: '预期失败', xpassed: '意外通过', incomplete: '未完成', pending: '未开始', running: '运行中' };
export const CHANGE_NAMES = { new_failure: '新增失败', recovered: '已恢复', persistent_failure: '持续失败', stable_pass: '持续通过', not_covered: '未覆盖 / 未完成', no_baseline: '无历史结果', other: '其他变化' };
const complete = new Set(['passed', 'failed', 'skipped', 'xfailed', 'xpassed']);
const active = run => ['queued', 'running'].includes(run?.state);
const finiteTime = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const logical = nodeid => nodeid.split('[')[0];
function operatorOf(result, item) {
  const values = [result.operator, item?.operator];
  for (const stage of result.stages || []) {
    values.push(stage.context?.operator, stage.context?.op_name);
    for (const property of stage.properties || []) if (['operator', 'op_name'].includes(property[0])) values.push(property[1]);
  }
  const names = [...new Set(values.filter(v => typeof v === 'string' && v.trim() && v.length <= 128).map(v => v.trim()))];
  return names.length > 1 ? '元数据冲突' : names[0] || '未标注算子';
}
export function resultRows(run, collection = []) {
  const metadata = new Map(collection.map(item => [item.nodeid, item]));
  const results = new Map((run?.test_results || []).map(item => [item.nodeid, item]));
  const ids = [...new Set(run?.request?.nodeids || [...results.keys()])];
  return ids.map(nodeid => {
    const item = metadata.get(nodeid), row = results.get(nodeid) || { nodeid };
    const outcome = Object.hasOwn(RESULT_NAMES, row.outcome) ? row.outcome : active(run) ? 'pending' : 'incomplete';
    const phases = [...new Set((row.stages || []).filter(s => s.outcome === 'failed').map(s => s.when).concat(row.failure_phase || []).filter(p => ['setup', 'call', 'teardown'].includes(p)))];
    return { ...row, nodeid, outcome, stages: row.stages || [], duration: finiteTime(row.duration) ? row.duration : 0, operator: operatorOf(row, item), logical: item?.logical_nodeid || logical(nodeid), failurePhases: phases,
      // Partial and missing durations are not ranked as completed test timings.
      measuredDuration: complete.has(outcome) && finiteTime(row.duration) && (row.stages?.length || row.timing_source) ? row.duration : null };
  });
}
export function compareResults(rows, parentRows, fallback = []) {
  const before = new Map(parentRows.map(row => [row.nodeid, row]));
  if (!before.size) for (const item of fallback) if (item.before) before.set(item.nodeid, { nodeid: item.nodeid, outcome: item.before });
  const after = new Map(rows.map(row => [row.nodeid, row]));
  return [...new Set([...before.keys(), ...after.keys()])].map(nodeid => {
    const a = before.get(nodeid), b = after.get(nodeid);
    const change = !b || !complete.has(b.outcome) ? 'not_covered' : !a ? 'no_baseline'
      : a.outcome === 'failed' && b.outcome === 'passed' ? 'recovered'
      : a.outcome === 'passed' && b.outcome === 'failed' ? 'new_failure'
      : a.outcome === 'failed' && b.outcome === 'failed' ? 'persistent_failure'
      : a.outcome === 'passed' && b.outcome === 'passed' ? 'stable_pass' : 'other';
    return { nodeid, before: a?.outcome || null, after: b?.outcome || null, change, selected: !!b };
  });
}
export function buildRunStatistics(run, collection = [], parent = null) {
  const rows = resultRows(run, collection);
  const counts = Object.fromEntries(Object.keys(RESULT_NAMES).map(outcome => [outcome, rows.filter(row => row.outcome === outcome).length]));
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row.operator)) groups.set(row.operator, { name: row.operator, total: 0, counts: Object.fromEntries(Object.keys(RESULT_NAMES).map(k => [k, 0])), duration: 0, timed: 0 });
    const group = groups.get(row.operator); group.total += 1; group.counts[row.outcome] += 1;
    if (row.measuredDuration !== null) { group.duration += row.measuredDuration; group.timed += 1; }
  }
  const completed = rows.filter(row => complete.has(row.outcome)).length;
  const measured = rows.filter(row => row.measuredDuration !== null);
  const changes = run.parent ? compareResults(rows, resultRows(parent || {}, collection), run.comparison) : [];
  const elapsed = finiteTime(run.started_at) && finiteTime(run.finished_at) && run.finished_at >= run.started_at ? run.finished_at - run.started_at : null;
  const identity = (a, b) => a == null || b == null ? null : JSON.stringify(a) === JSON.stringify(b);
  return { rows, counts, total: rows.length, completed,
    passRate: counts.passed + counts.failed ? counts.passed / (counts.passed + counts.failed) : null,
    coverage: rows.length ? completed / rows.length : null,
    operatorCount: [...groups.keys()].filter(k => !['未标注算子', '元数据冲突'].includes(k)).length,
    unlabelled: rows.filter(r => r.operator === '未标注算子').length,
    logicalCount: new Set(rows.map(row => row.logical)).size, groups: [...groups.values()],
    phases: ['setup', 'call', 'teardown'].map(phase => ({ phase, count: rows.filter(row => row.outcome === 'failed' && row.failurePhases.includes(phase)).length })),
    slowest: [...measured].sort((a, b) => b.measuredDuration - a.measuredDuration).slice(0, 10),
    measuredCount: measured.length, cumulativeDuration: measured.reduce((sum, r) => sum + r.measuredDuration, 0), elapsed,
    changes, changeCounts: Object.fromEntries(Object.keys(CHANGE_NAMES).map(key => [key, changes.filter(c => c.change === key).length])),
    comparisonScope: parent ? 'parent' : 'selected',
    sameSource: identity(run.source_snapshot?.sha256, parent?.source_snapshot?.sha256),
    sameEnvironment: identity(run.runtime || run.request?.environment, parent?.runtime || parent?.request?.environment) };
}
export function filterStatisticRows(stats, filter = {}) {
  const changed = filter.change ? new Set(stats.changes.filter(c => c.change === filter.change).map(c => c.nodeid)) : null;
  return stats.rows.filter(row => (!filter.status || row.outcome === filter.status) && (!filter.operator || row.operator === filter.operator)
    && (!filter.phase || row.outcome === 'failed' && row.failurePhases.includes(filter.phase))
    && (!filter.nodeid || row.nodeid === filter.nodeid) && (!changed || changed.has(row.nodeid)));
}
export function demoStatisticsRecord(run, cases) {
  const test_results = [...new Set(run.caseIds)].map(id => {
    const item = cases.find(c => c.id === id);
    const outcome = active(run) ? run.state === 'queued' ? 'pending' : 'running'
      : ['cancelled', 'interrupted', 'timeout', 'error'].includes(run.state) ? 'incomplete' : run.failedIds.includes(id) ? 'failed' : 'passed';
    return { nodeid: item?.name || id, operator: id, outcome, failure_phase: outcome === 'failed' ? 'call' : null, stages: [] };
  });
  return { id: run.id, parent: run.parent, state: run.state, source: 'browser-demo', request: { nodeids: test_results.map(r => r.nodeid) }, test_results };
}
