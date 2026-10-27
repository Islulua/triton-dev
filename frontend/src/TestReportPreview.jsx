import { useEffect, useMemo, useState } from 'react';
import { IconDownload, IconFileCode, IconFileReport } from '@tabler/icons-react';
import { downloadJson } from './api';
import { buildTestReport, groupReportRows, filterReportRows, REPORT_STATUS, reportTime, testReportHtml } from './test-report';
import './test-report.css';
const seconds = value => value == null ? '—' : `${value.toFixed(3)} s`;
function ResultBlock({ status, title }) { return <span className={`case-result-block ${status}`} title={title || REPORT_STATUS[status]}>{status}</span>; }
function GroupResults({ rows }) {
  const counts = Object.keys(REPORT_STATUS).map(status => [status, rows.filter(r => r.status === status).length]).filter(([, n]) => n);
  return <span className="case-report-group-counts">{counts.map(([status, count]) => <span key={status}><ResultBlock status={status}/><b>{count}</b></span>)}</span>;
}
export function TestReportPreview({ record, collection = [], onInspect }) {
  const report = useMemo(() => buildTestReport(record, collection), [record, collection]);
  const [query, setQuery] = useState(''), [status, setStatus] = useState('all');
  const [openGroups, setOpenGroups] = useState(new Set()), [expandedRows, setExpandedRows] = useState(new Set());
  const visible = filterReportRows(report.rows, query, status), files = groupReportRows(visible);
  const toggle = (key, setter) => setter(old => { const next = new Set(old); next.has(key) ? next.delete(key) : next.add(key); return next; });
  useEffect(() => { setOpenGroups(new Set()); setExpandedRows(new Set()); }, [record.id]);
  const environment = record.request?.environment;
  const exportHtml = () => {
    const url = URL.createObjectURL(new Blob([testReportHtml(record, collection)], { type: 'text/html;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `${record.id}-case-report.html`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="case-report" aria-label="逐配置测试报告">
    <div className="case-report-heading"><div>{record.source === 'browser-demo'&&<span className="source-label">演示数据</span>}<h2>报告概览</h2><p className="mono" title={record.id}>运行 {record.id.slice(-12)}</p></div><div className="toolbar-actions"><button className="button" onClick={exportHtml}><IconDownload size={16}/>导出 HTML</button><button className="button" onClick={() => downloadJson(`${record.id}-case-report.json`, { schema_version: 1, source: record.source === 'browser-demo' ? 'browser-demo' : 'pytest-task-record', run_id: record.id, ...report })}><IconDownload size={16}/>导出 JSON</button></div></div>
    {record.error && <div className="error-banner" role="alert">{record.error.code}：{record.error.message}</div>}
    <div className="case-report-context"><span>{record.job_id||'浏览器演示'}</span><span>{reportTime(report.startedAt)}</span><span>耗时 {seconds(report.elapsed)}</span></div>
    <details className="ui-disclosure"><summary>运行信息与统计口径</summary>    <div className="case-report-meta"><span><b>项目</b>{record.job_id || '浏览器演示'}</span><span><b>运行状态</b>{record.state}</span><span><b>开始</b>{reportTime(report.startedAt)}</span><span><b>结束</b>{reportTime(report.endedAt)}</span><span><b>批次耗时</b>{seconds(report.elapsed)}</span><span><b>源码快照</b><code>{record.source_snapshot?.sha256?.slice(0, 16) || '未记录'}</code></span><span><b>环境</b>{environment?.name || environment?.sdk_name || (record.runtime?.python ? `Python ${record.runtime.python.split(' ')[0]}` : '未记录')}</span><span><b>执行方式</b>{record.request?.isolation || '浏览器演示'}{record.request?.workers ? ` × ${record.request.workers}` : ''}</span><span><b>退出码</b>{record.result?.returncode ?? '未记录'}</span><span><b>父运行</b><code>{record.parent || '首次运行'}</code></span></div>
    <p className="case-report-note">{record.source === 'browser-demo' ? '演示记录未执行真实 kernel，未采集的时间与文件路径留空。' : '结果来自所选运行记录；设备与数值验证以具体 case 的原始证据为准。'} 时区：{Intl.DateTimeFormat().resolvedOptions().timeZone}。配置耗时为已记录阶段累计工时；开始/结束采用实际事件时间，缺失时不推算。</p>
</details>
    <div className="case-report-legend">{Object.entries(report.counts).filter(([, count]) => count > 0).map(([key, count]) => <button key={key} className={status === key ? 'selected' : ''} disabled={!count} onClick={() => setStatus(old => old === key ? 'all' : key)} title={REPORT_STATUS[key]}><ResultBlock status={key}/><b>{count}</b></button>)}</div>
    <div className="case-report-tools"><input aria-label="搜索报告配置" placeholder="搜索文件、用例、配置、算子或参数…" value={query} onChange={e => setQuery(e.target.value)}/><select aria-label="报告结果筛选" value={status} onChange={e => setStatus(e.target.value)}><option value="all">全部结果</option>{Object.entries(REPORT_STATUS).map(([key, name]) => <option key={key} value={key}>{key} · {name}</option>)}</select><button className="button" onClick={() => setOpenGroups(new Set(files.flatMap(file => [`file:${file.name}`, ...file.cases.map(c => `case:${c.id}`)])))}>展开全部</button><button className="button" onClick={() => { setOpenGroups(new Set()); setExpandedRows(new Set()); }}>折叠全部</button></div>
    <div className="case-report-scope">{report.total} 配置 · {report.files.length} 文件 · 当前显示 {visible.length} 配置{(query || status !== 'all') && <button className="text-button" onClick={() => { setQuery(''); setStatus('all'); }}>清除筛选</button>}</div>
    {!visible.length && <div className="case-report-empty">没有匹配配置。空结果不表示通过。</div>}
    {files.map(file => <details className="case-report-file" open={openGroups.has(`file:${file.name}`)} key={file.name}><summary onClick={e => { e.preventDefault(); toggle(`file:${file.name}`, setOpenGroups); }}><IconFileCode size={19}/><strong>{file.name}</strong><span>{file.cases.length} 用例 · {file.rows.length} 配置</span><GroupResults rows={file.rows}/></summary><div className="case-report-file-body">{file.cases.map(test => <details className="case-report-test" open={openGroups.has(`case:${test.id}`)} key={test.id}><summary onClick={e => { e.preventDefault(); toggle(`case:${test.id}`, setOpenGroups); }}><strong>{test.name}</strong><span>{test.rows.length} 配置</span><GroupResults rows={test.rows}/></summary><div className="case-report-table-scroll"><table className="case-report-table"><thead><tr><th>配置 / 参数</th><th>结果</th><th>开始时间</th><th>结束 / 最后报告</th><th>阶段耗时</th><th>Worker</th><th>失败阶段</th><th>操作</th></tr></thead><tbody>{test.rows.map(row => <ReportConfiguration key={row.nodeid} row={row} expanded={expandedRows.has(row.nodeid)} onToggle={() => toggle(row.nodeid, setExpandedRows)} onInspect={onInspect}/>)}</tbody></table></div></details>)}</div></details>)}
    <details className="ui-disclosure"><summary>结果判定说明</summary><p className="case-report-note">CRASH 仅指有 test_started 与对应 worker 异常退出证据、且没有完成 teardown 的配置，不把其余未执行项标成崩溃。报告展示状态与原始 outcome 分开保留，FAIL / SKIP / XFAIL / XPASS 也不互相合并。</p></details>
  </section>;
}
function ReportConfiguration({ row, expanded, onToggle, onInspect }) {
  const parameters = Object.entries(row.parameters).map(([key, value]) => `${key}=${value}`).join(' · ');
  return <><tr className="case-report-config"><td><strong>{row.parameter || '默认配置'}</strong><span title={parameters}>{parameters || '无已记录参数'}</span><small>{row.operator}</small></td><td><ResultBlock status={row.status} title={`${REPORT_STATUS[row.status]}；原始 outcome=${row.outcome}`}/></td><td>{reportTime(row.startedAt)}</td><td>{reportTime(row.endedAt)}</td><td>{seconds(row.duration)}</td><td className="mono">{row.workers.join(', ') || '—'}</td><td>{row.failurePhases.join(', ') || (row.status === 'CRASH' ? '异常退出' : '—')}</td><td><button className="text-button" aria-label={`查看报告配置 ${row.nodeid}`} aria-expanded={expanded} onClick={onToggle}>{expanded ? '收起' : '详细信息'}</button></td></tr>{expanded && <tr className="case-report-expanded"><td colSpan="8"><dl><dt>Node ID</dt><dd className="mono">{row.nodeid}</dd><dt>位置 / 逻辑 ID</dt><dd>{row.file}{row.line ? `:${row.line}` : ''} · {row.caseId || '未标注'}</dd><dt>结果依据</dt><dd>{row.crashEvidence ? `worker ${row.crashEvidence.worker} 异常退出：${row.crashEvidence.reason}` : `${REPORT_STATUS[row.status]} · 原始 outcome=${row.outcome}`}</dd><dt>PID / Markers</dt><dd>{row.pids.join(', ') || '未记录'} · {row.markers.join(', ') || '—'}</dd><dt>Fixtures</dt><dd>{row.fixtures.join(', ') || '未记录'}</dd></dl>{row.reason && <pre>{row.reason}</pre>}<details><summary>阶段原始数据 / context / properties</summary><pre>{JSON.stringify(row.stages, null, 2)}</pre></details>{onInspect && <button className="button" onClick={() => onInspect({ nodeid: row.nodeid })}>前往阶段明细</button>}</td></tr>}</>;
}
export function ReportsWorkspace({ records, demo = false, onSettings, onRun }) {
  const runs = records.filter(r => demo || r.request?.kind === 'pytest' && r.request?.operation === 'run').sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  const [project, setProject] = useState('all'), [selected, setSelected] = useState('');
  const projects = [...new Set(runs.map(r => r.job_id || 'browser-demo'))];
  const options = runs.filter(r => project === 'all' || (r.job_id || 'browser-demo') === project);
  const record = options.find(r => r.id === selected) || options[0];
  useEffect(() => { if (record && record.id !== selected) setSelected(record.id); }, [record?.id, selected]);
  const collection = record && records.find(r => r.id === record.request?.source_id)?.collection || [];
  return <div className="reports-workspace"><div className="reports-selectors"><label>测试项目<select aria-label="报告测试项目" value={project} onChange={e => { setProject(e.target.value); setSelected(''); }}><option value="all">全部项目</option>{projects.map(name => <option key={name}>{name}</option>)}</select></label><label>运行记录<select aria-label="报告运行记录" value={record?.id || ''} onChange={e => setSelected(e.target.value)}>{!options.length && <option value="">尚无可预览记录</option>}{options.map(r => <option key={r.id} value={r.id}>{r.job_id || '浏览器演示'} · {reportTime(r.started_at || r.created_at)} · {r.id.slice(-12)} · {r.state}</option>)}</select></label></div>{demo && <div className="info"><IconFileReport size={18}/><span>当前为浏览器演示报告。连接本地 API 可预览真实 pytest 记录。</span><button className="text-button" onClick={onSettings}>连接服务</button></div>}{record ? <TestReportPreview key={record.id} record={record} collection={collection}/> : <div className="ui-empty"><h3>尚无测试报告</h3><p>运行用例后，在这里查看逐配置结果。</p>{onRun&&<button className="button primary" onClick={onRun}>前往运行用例</button>}</div>}</div>;
}
