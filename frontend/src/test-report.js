import { resultRows } from './run-statistics.js';
export const REPORT_STATUS = {
  PASS: '通过', FAIL: '测试失败', CRASH: '执行进程异常退出', SKIP: '跳过', XFAIL: '预期失败', XPASS: '意外通过',
  TIMEOUT: '运行超时', CANCELLED: '已取消', INCOMPLETE: '结果未完整', PENDING: '尚未开始', RUNNING: '运行中',
};
const complete = new Set(['passed', 'failed', 'skipped', 'xfailed', 'xpassed']);
const validTime = n => typeof n === 'number' && Number.isFinite(n) && n >= 0;
export function reportCrashEvidence(record) {
  const evidence = new Map();
  if (['cancelled', 'timeout'].includes(record.state)) return evidence;
  const starts = (record.stages || []).filter(e => e.type === 'test_started' && e.nodeid && validTime(e.time));
  for (const exit of (record.stages || []).filter(e => e.type === 'worker_exit' && e.error && validTime(e.time))) {
    const start = starts.filter(e => e.worker_id === exit.target_worker_id && e.time <= exit.time).sort((a, b) => b.time - a.time)[0];
    if (!start) continue;
    const completed = (record.stages || []).some(e => e.type === 'stage' && e.nodeid === start.nodeid
      && e.worker_id === start.worker_id && e.when === 'teardown' && validTime(e.time) && e.time >= start.time && e.time <= exit.time);
    if (!completed) evidence.set(start.nodeid, { worker: start.worker_id, time: exit.time, reason: String(exit.error), start });
  }
  return evidence;
}
export function buildTestReport(record, collection = []) {
  const metadata = new Map(collection.map(item => [item.nodeid, item]));
  const crashes = reportCrashEvidence(record);
  const original = new Map((record.test_results || []).map(row => [row.nodeid, row]));
  const rows = resultRows(record, collection).map(row => {
    const item = metadata.get(row.nodeid), crash = crashes.get(row.nodeid);
    const starts = (record.stages || []).filter(e => e.type === 'test_started' && e.nodeid === row.nodeid && validTime(e.time));
    const startedAt = starts.length ? Math.min(...starts.map(e => e.time)) : null;
    const timedStages = row.stages.filter(s => validTime(s.time));
    const endedAt = crash?.time ?? (complete.has(row.outcome) && timedStages.length ? Math.max(...timedStages.map(s => s.time)) : null);
    let status = { passed: 'PASS', failed: 'FAIL', skipped: 'SKIP', xfailed: 'XFAIL', xpassed: 'XPASS', pending: 'PENDING', running: 'RUNNING', incomplete: 'INCOMPLETE' }[row.outcome] || 'INCOMPLETE';
    if (crash && row.outcome !== 'passed' && !row.stages.some(s => s.when === 'teardown')) status = 'CRASH';
    else if (!complete.has(row.outcome) && (startedAt !== null || row.stages.length)) {
      if (record.state === 'timeout') status = 'TIMEOUT';
      else if (record.state === 'cancelled') status = 'CANCELLED';
    }
    const rawDuration = original.get(row.nodeid)?.duration;
    const observedDurations = row.stages.map(s => s.duration).filter(validTime);
    const duration = row.stages.length && validTime(rawDuration) ? rawDuration
      : observedDurations.length ? observedDurations.reduce((sum, value) => sum + value, 0) : null;
    const file = row.nodeid.includes('::') ? row.nodeid.split('::')[0] : '未记录文件';
    const logical = item?.logical_nodeid || row.logical;
    const name = logical.startsWith(file + '::') ? logical.slice(file.length + 2) : logical;
    const parameter = item?.parameter_id ?? (row.nodeid.startsWith(logical + '[') ? row.nodeid.slice(logical.length + 1, -1) : '默认配置');
    const failure = row.stages.find(s => s.outcome === 'failed' && s.longrepr);
    const skipped = row.stages.find(s => s.outcome === 'skipped' && s.longrepr);
    const reason = crash?.reason || failure?.longrepr || skipped?.longrepr || (status === 'INCOMPLETE' ? (startedAt === null && !row.stages.length ? '本次未执行或未收到开始事件，不能判定通过或崩溃。' : '缺少完整结果，未观察到可归属的 worker 崩溃证据。') : '');
    return { ...row, file, logical, name, parameter, parameters: item?.parameters || {},
      caseId: item?.case_id || null, markers: item?.markers || [], fixtures: item?.fixtures || [], line: item?.line ?? null,
      status, startedAt, endedAt, duration,
      workers: [...new Set([...(row.workers || []), ...row.stages.map(s => s.worker_id), ...starts.map(s => s.worker_id)].filter(Boolean))],
      pids: [...new Set([...row.stages, ...starts].map(s => s.pid).filter(Boolean))], reason,
      crashEvidence: crash || null, source: record.source === 'browser-demo' ? 'browser-demo' : 'pytest-task-record' };
  });
  return { rows, counts: Object.fromEntries(Object.keys(REPORT_STATUS).map(key => [key, rows.filter(row => row.status === key).length])),
    files: groupReportRows(rows), total: rows.length,
    startedAt: validTime(record.started_at) ? record.started_at : null,
    endedAt: validTime(record.finished_at) ? record.finished_at : null,
    elapsed: validTime(record.started_at) && validTime(record.finished_at) && record.finished_at >= record.started_at ? record.finished_at - record.started_at : null };
}
export function groupReportRows(rows) {
  const files = new Map();
  for (const row of rows) {
    if (!files.has(row.file)) files.set(row.file, { name: row.file, rows: [], cases: new Map() });
    const file = files.get(row.file); file.rows.push(row);
    if (!file.cases.has(row.logical)) file.cases.set(row.logical, { id: row.logical, name: row.name, rows: [] });
    file.cases.get(row.logical).rows.push(row);
  }
  return [...files.values()].map(file => ({ ...file, cases: [...file.cases.values()] }));
}
export function filterReportRows(rows, query = '', status = 'all') {
  const search = query.toLowerCase().trim();
  return rows.filter(row => (status === 'all' || row.status === status)
    && `${row.nodeid} ${row.operator} ${row.caseId || ''} ${JSON.stringify(row.parameters)}`.toLowerCase().includes(search));
}
export function reportTime(value) {
  return value == null ? '—' : new Date(value * 1000).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3, hour12: false });
}
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export function testReportHtml(record, collection = []) {
  const report = buildTestReport(record, collection);
  const status = row => `<span class="badge ${row.status}">${row.status}</span>`;
  const files = report.files.map(file => `<section><h2>${escape(file.name)} · ${file.rows.length} 配置</h2>${file.cases.map(item => `<details open><summary>${escape(item.name)} · ${item.rows.length} 配置</summary><div class="scroll"><table><thead><tr><th>配置 / 参数</th><th>结果</th><th>开始时间</th><th>结束时间</th><th>阶段耗时</th><th>Worker / 失败阶段</th></tr></thead><tbody>${item.rows.map(row => `<tr><td><b>${escape(row.parameter)}</b><small>${escape(JSON.stringify(row.parameters))}</small><small>${escape(row.nodeid)}</small></td><td>${status(row)}</td><td>${escape(reportTime(row.startedAt))}</td><td>${escape(reportTime(row.endedAt))}</td><td>${row.duration == null ? '—' : row.duration.toFixed(3) + ' s'}</td><td>${escape(row.workers.join(', ') || '—')} / ${escape(row.failurePhases.join(', ') || '—')}</td></tr>${row.reason ? `<tr><td colspan="6"><details><summary>结果说明 / 原始证据</summary><pre>${escape(row.reason)}</pre></details></td></tr>` : ''}`).join('')}</tbody></table></div></details>`).join('')}</section>`).join('');
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>测试报告 ${escape(record.id)}</title><style>body{font:13px/1.8 system-ui,sans-serif;background:#f5f8f7;color:#365462;margin:0;padding:28px}main{max-width:1400px;margin:auto}section{background:white;border:1px solid #dfe8e4;border-radius:6px;padding:20px;margin:20px 0}h1{font-size:24px}h2{font-size:17px}summary{cursor:pointer;font-weight:600;padding:12px 0}table{width:100%;border-collapse:collapse;min-width:880px}th,td{border:1px solid #e4ece8;padding:12px;text-align:left;vertical-align:top}th{background:#f4f8f6}td:first-child{max-width:320px;overflow-wrap:anywhere}small{display:block;color:#82979f;font-size:11px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}.scroll{overflow:auto}.badge{display:inline-block;color:white;background:#83939d;border-radius:4px;padding:3px 10px;min-width:65px;text-align:center;font:bold 11px/1.8 ui-monospace,monospace}.PASS{background:#257d65}.FAIL{background:#b84949}.CRASH{background:#793c79}.TIMEOUT{background:#996320}.XFAIL{background:#9a7b2c}.XPASS{background:#526ea4}.INCOMPLETE{background:#9b784b}.RUNNING{background:#2d8195}.notice{padding:14px;background:#fff6df;border-radius:5px}@media print{body{padding:0;background:white}details{break-inside:auto}.scroll{overflow:visible}table{min-width:0;font-size:10px}}</style><main><h1>逐配置测试报告</h1><p>${escape(record.id)} · ${escape(record.job_id || record.source || '未记录项目')}<br>开始 ${escape(reportTime(report.startedAt))} · 结束 ${escape(reportTime(report.endedAt))} · 墙钟耗时 ${report.elapsed == null ? '—' : report.elapsed.toFixed(3) + ' s'}<br>时区 ${escape(Intl.DateTimeFormat().resolvedOptions().timeZone)}</p><p class="notice">来源：${record.source === 'browser-demo' ? '浏览器演示，没有执行真实 kernel' : 'pytest 运行记录；真实设备与数值验证以具体case证据为准'}。CRASH仅用于有开始事件与worker异常退出证据且未完成的配置；原始outcome保持不变。配置耗时为已记录阶段工时，缺失时间留空，不补造结果。</p><p>共 ${report.total} 配置 · ${report.files.length} 文件 · ${Object.entries(report.counts).filter(([, n]) => n).map(([key, n]) => escape(key) + ' ' + n).join(' / ')}</p>${files}</main></html>`;
}
