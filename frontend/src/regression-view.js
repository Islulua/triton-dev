// Derive display facts only from persisted experiments; no invented progress or outcomes.
export const isActive = record => !!record && ['queued', 'running'].includes(record.state);
export const outcomeLabel = { passed: 'PASS', target_failure: 'FAIL', unavailable: 'UNKNOWN', different_failure: 'OTHER', unstable: 'FLAKY', pending: 'RUNNING', running: 'RUNNING', cancelled: 'CANCELLED', interrupted: 'INTERRUPTED' };
export function repeatOutcome(rows, repeats) {
  if (!rows.length) return 'untested';
  const completed = rows.filter(r => !['pending', 'interrupted', 'cancelled'].includes(r.classification));
  const latest = new Map(completed.map(row => [row.repeat, row]));
  const values = [...latest.values()].map(r => r.classification);
  if (new Set(values).size > 1) return 'unstable';
  if (latest.size < repeats) return rows.some(r => r.classification === 'pending') ? 'running' : 'incomplete';
  return values[0];
}
export function regressionView(record) {
  const r = record, rows = r.experiments || [], repeats = r.spec.repeats;
  const baseline = rows.filter(e => e.label === 'baseline'), latest = rows.filter(e => e.label === 'latest');
  const baselineOutcome = repeatOutcome(baseline, repeats), latestOutcome = repeatOutcome(latest, repeats);
  const versions = (r.inventory || []).map(v => {
    const experiments = rows.filter(e => e.label === v.id || e.label === (v.id === r.spec.baseline ? 'baseline' : v.id === r.target?.id ? 'latest' : '__none__'));
    return { ...v, outcome: repeatOutcome(experiments, repeats), experiments,
      baseline: v.id === r.spec.baseline, latest: v.id === r.target?.id,
      good: v.id === r.boundary?.good.id, bad: v.id === r.boundary?.bad.id };
  });
  const events = r.events || [];
  const phaseAt = e => events.filter(event => event.time <= e.started_at).at(-1)?.phase;
  let lo = (r.inventory || []).findIndex(v => v.id === r.spec.baseline), hi = (r.inventory || []).length - 1;
  const seen = new Set(), rounds = [];
  for (const e of rows) {
    if (phaseAt(e) !== 'search' || seen.has(e.label)) continue;
    const index = versions.findIndex(v => v.id === e.label);
    if (index < 0) continue;
    seen.add(e.label);
    const group = rows.filter(x => x.label === e.label), outcome = repeatOutcome(group, repeats);
    if (outcome === 'passed') lo = index;
    if (outcome === 'target_failure') hi = index;
    rounds.push({ sdk: e.label, outcome, evidence: group.map(x => x.id),
      interval: lo >= 0 && hi >= lo ? [r.inventory[lo].id, r.inventory[hi].id] : null });
  }
  const supported = (r.attribution || []).find(a => a.supported);
  const stopped = !isActive(r), componentDone = ['component_supported', 'group_supported'].includes(r.result) && !!supported;
  const status = (done, started, failed = false) => done ? 'done' : failed ? 'blocked' : started ? (stopped ? 'stopped' : 'active') : 'waiting';
  const steps = [
    { label: '基线通过', state: status(baselineOutcome === 'passed', baseline.length || r.phase === 'baseline', baselineOutcome !== 'passed' && baselineOutcome !== 'running' && baselineOutcome !== 'untested'), detail: `${baseline.filter(e => e.classification === 'passed').length}/${repeats} PASS` },
    { label: latestOutcome === 'passed' ? '最新通过' : latestOutcome === 'target_failure' ? '最新失败' : '最新验证', state: status(['passed', 'target_failure'].includes(latestOutcome), latest.length || ['update', 'latest'].includes(r.phase), ['unstable', 'unavailable', 'different_failure'].includes(latestOutcome)), detail: latest.length ? `${latest.length} 次 · ${outcomeLabel[latestOutcome] || '未完成'}` : '等待更新验证' },
    { label: '日期定位', state: status(!!r.boundary && rows.some(e => e.label === 'audit_bad') && repeatOutcome(rows.filter(e => e.label === 'audit_bad'), repeats) === 'target_failure', !!r.boundary || rounds.length), detail: r.boundary ? `${shortSdk(r.boundary.good.id)} → ${shortSdk(r.boundary.bad.id)}` : '等待搜索' },
    { label: '组件定位', state: status(componentDone, (r.attribution || []).length || r.phase === 'components'), detail: componentDone ? `${supported.components.join(' + ')} 双向验证` : '等待干预证据' },
    { label: '报告就绪', state: stopped ? 'done' : 'waiting', detail: stopped ? '当前证据与限制' : '等待调查结束' },
  ];
  if (r.state === 'completed' && r.result === 'no_regression' && baselineOutcome === 'passed' && latestOutcome === 'passed') for (const i of [2, 3]) Object.assign(steps[i], { state: 'skipped', detail: '无需执行' });
  return { versions, rounds, supported: componentDone ? supported : null, steps, baselineOutcome, latestOutcome };
}
export function shortSdk(value = '') { return value.match(/(\d{4})(\d{2})(\d{2})$/)?.slice(2).join('-') || value; }
export function heroText(record, view) {
  const component = view.supported?.components.join(' + ');
  if (record.state === 'error') return { title: '调查遇到执行问题', description: record.error?.message || '请查看实验与错误证据后恢复调查。', tone: 'warning' };
  if (isActive(record)) return { title: record.boundary ? `正在缩小回归范围：${shortSdk(record.boundary.good.id)} ～ ${shortSdk(record.boundary.bad.id)}` : '正在验证基线与最新环境', description: '实验按固定场景执行；完成后展示可验证的版本边界和组件关联。', tone: 'running' };
  if (['component_supported', 'group_supported'].includes(record.result) && component) return { title: `已定位回归：${component} 版本变更关联`, description: '新版换入后失败，旧版回退后恢复，双向实验支持。', tone: 'supported' };
  if (record.result === 'no_regression') return { title: '最新环境通过，本次未发现回归', description: '所选配置在本次基线与最新环境的重复实验中均通过。未执行日期搜索和组件干预。', tone: 'supported' };
  if (record.result === 'baseline_invalid') return { title: '基线未通过，已停止回归查找', description: '请先修复或更换基线；尚未更新到最新SDK，不进行组件归因。', tone: 'warning' };
  if (record.result === 'unstable') return { title: '结果存在波动，暂不作确定归因', description: '重复实验出现冲突，需先确认偶现条件，再继续定位。', tone: 'warning' };
  if (record.boundary) return { title: '已找到版本范围，组件尚未确认', description: `当前任务${record.state === 'budget_exhausted' ? '预算已用尽' : record.state === 'cancelled' ? '已取消' : '已停止'}；保留好坏版本证据，不将未完成实验写成结论。`, tone: 'warning' };
  return { title: '当前证据不足，尚未确认回归', description: '查看原始实验、停止原因和缺失证据；没有完整结果不代表通过。', tone: 'warning' };
}
