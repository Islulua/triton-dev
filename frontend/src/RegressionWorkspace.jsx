import { useEffect, useState } from 'react';
import { IconPlayerPlay, IconDownload, IconRefresh, IconPlayerStop, IconPlus, IconCheck, IconChevronDown, IconChevronRight, IconCircleCheckFilled, IconCircle, IconAlertCircle, IconLoader2, IconCopy, IconFileText } from '@tabler/icons-react';
import { request, downloadJson } from './api';
import './regression.css';
import { DEMO_STEPS, DEMO_CATALOG, regressionDemo, demoEvidence, demoReport } from './regression-demo';
import { regressionView, heroText, shortSdk, outcomeLabel } from './regression-view';
const active = r => r && ['queued', 'running'].includes(r.state);
const statuses = { passed: 'PASS', target_failure: 'FAIL', unavailable: 'UNKNOWN', different_failure: 'OTHER', unstable: 'FLAKY', pending: 'RUNNING', cancelled: 'CANCELLED', interrupted: 'INTERRUPTED' };
const phases = { created: '登记任务', baseline: '基线校准', update: '更新并锁定SDK', latest: '最新版本验证', search: '二分搜索', audit_history: '首次失败审计', audit_boundary: '边界复验', components: '组件定位' };
const results = { no_regression: '未发现回归', baseline_invalid: '基线无效', unstable: '结果不稳定', inconclusive: '证据不足', boundary_found: '已找到版本边界', component_supported: '单组件双向支持', group_supported: '组件组双向支持', incomplete: '调查尚未完成' };
function downloadText(name, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function RegressionWorkspace({ token, onSettings, multiUser = false }) {
  const [catalog, setCatalog] = useState(null), [records, setRecords] = useState([]), [selected, setSelected] = useState('');
  const [scenario, setScenario] = useState('component'), [baseline, setBaseline] = useState('mock-sdk-20261010');
  const [mode, setMode] = useState('earliest_verified'), [repeat, setRepeat] = useState(2), [budget, setBudget] = useState(60);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [evidence, setEvidence] = useState(null), [report, setReport] = useState(null), [tab, setTab] = useState('experiments');
  const [configOpen, setConfigOpen] = useState(false), [copied, setCopied] = useState('');
  const [demoStep, setDemoStep] = useState(DEMO_STEPS.length - 1), [playing, setPlaying] = useState(false);
  const offline = !token;
  const [personalProfiles, setPersonalProfiles] = useState([]), [profileId, setProfileId] = useState('');
  useEffect(() => { if (!multiUser || !token) return; let alive = true; request('/me/ai-profiles').then(rows => {if (alive) {setPersonalProfiles(rows);setProfileId(rows.find(r=>r.is_default&&r.enabled)?.id || '');}}).catch(()=>{});return()=>{alive=false}; }, [token, multiUser]);
  const record = offline ? regressionDemo(demoStep) : records.find(r => r.id === selected) || records[0];
  const shownCatalog = offline ? DEMO_CATALOG : catalog;
  const shownRecords = offline ? [record] : records;
  useEffect(() => {
    if (!offline || !playing) return;
    if (demoStep >= DEMO_STEPS.length - 1) { setPlaying(false); return; }
    const timer = setTimeout(() => setDemoStep(i => Math.min(i + 1, DEMO_STEPS.length - 1)), 1200);
    return () => clearTimeout(timer);
  }, [offline, playing, demoStep]);
  useEffect(() => { setPlaying(false); }, [token]);
  useEffect(() => { if (offline) { setEvidence(null); setReport(null); setTab('experiments'); } }, [offline, demoStep]);
  function playDemo() { if (demoStep >= DEMO_STEPS.length - 1) setDemoStep(0); setPlaying(true); setEvidence(null); setReport(null); }

  useEffect(() => {
    setCatalog(null); setRecords([]); setEvidence(null); setReport(null); setError('');
    if (!token) return;
    let alive = true, pending = false;
    async function refresh() {
      if (pending) return; pending = true;
      try {
        const [c, r] = await Promise.all([request('/regression/catalog', { token }), request('/regression/tasks', { token })]);
        if (alive) { setCatalog(c); setRecords(r); }
      } catch (e) { if (alive) setError(e.message); }
      finally { pending = false; }
    }
    refresh(); const timer = setInterval(refresh, 1200);
    return () => { alive = false; clearInterval(timer); };
  }, [token]);
  useEffect(() => { setEvidence(null); setReport(null); setTab('experiments'); }, [record?.id]);
  useEffect(() => {
    if (!token || !record || active(record)) return;
    let alive = true;
    request(`/regression/tasks/${record.id}/report`, { token }).then(value => { if (alive) setReport(value); }).catch(() => {});
    return () => { alive = false; };
  }, [token, record?.id, record?.state]);
  async function action(path, body) {
    if (offline) { setPlaying(false); return; }
    setBusy(true); setError('');
    try {
      const r = await request(path, { token, method: 'POST', body });
      setRecords(old => [r, ...old.filter(x => x.id !== r.id)]); setSelected(r.id); setReport(null); setConfigOpen(false);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function downloadBundle() {
    if (offline) { downloadJson('regression-browser-demo.json', record); return; }
    setError('');
    try {
      const response = await fetch(`/api/regression/tasks/${record.id}/bundle`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error('证据包尚未就绪或服务连接失败。');
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement('a'); a.href = url; a.download = `${record.id}-evidence.tar.gz`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message); }
  }
  async function viewReport() {
    try { setReport(offline ? demoReport(record) : await request(`/regression/tasks/${record.id}/report`, { token })); setTab('report'); }
    catch (e) { setError(e.message); }
  }
  async function inspect(id) {
    try { setEvidence(offline ? demoEvidence(record, id) : { id, ...await request(`/regression/tasks/${record.id}/experiments/${id}`, { token }) }); }
    catch (e) { setError(e.message); }
  }
  const view = record ? regressionView(record) : null, factHero = record ? heroText(record, view) : null;
  const hero = offline ? { ...factHero, title: active(record) ? `演示阶段：${DEMO_STEPS[demoStep][1]}` : '演示结果：cmodel 版本变更关联', description: active(record) ? DEMO_STEPS[demoStep][2] : '预设样例中，新版换入失败、旧版回退恢复；当前未执行测试。' } : factHero;
  async function copyText(text, kind) {
    try { await navigator.clipboard.writeText(text); setCopied(kind); setTimeout(() => setCopied(''), 2000); }
    catch { setError('复制未成功，请从调研报告中手动复制。'); }
  }
  async function getReport() { if (offline) return demoReport(record); return report || await request(`/regression/tasks/${record.id}/report`, { token }); }
  async function downloadReport() {
    try { const data = await getReport(); setReport(data); downloadText(`${record.id}-report.md`, data.markdown); }
    catch (e) { setError(e.message); }
  }
  async function copyCommand() {
    try { const data = await getReport(); setReport(data); const command = data.markdown.split('```bash\n')[1]?.split('\n```')[0]; if (!command || command.includes('暂无')) throw new Error('尚无失败实验可重放。'); await copyText(command, 'command'); }
    catch (e) { setError(e.message); }
  }
  const issueSummary = record ? `${hero.title}\n${hero.description}\n基线：${record.spec.baseline}；最新：${record.target?.id || '未更新'}\n好坏范围：${record.boundary ? `${record.boundary.good.id} → ${record.boundary.bad.id}` : '未确认'}\n严格最早失败：${record.earliest_proven ? '已确认' : '未证明'}\n任务：${record.id}\n范围：${offline ? '浏览器预设回放，未执行pytest或调用模型' : 'mock SDK/模型 + 真实CPU pytest'}，非板卡/源码根因结论。` : '';
  const noRegression = record?.state === 'completed' && record?.result === 'no_regression' && view?.baselineOutcome === 'passed' && view?.latestOutcome === 'passed';
  return <div className="regression-workspace">
    <div className="regression-page-heading"><div><h1>回归定位</h1></div><button className="button" aria-expanded={configOpen} onClick={() => offline ? onSettings() : setConfigOpen(!configOpen)}><IconPlus size={16}/>{offline ? '连接服务运行' : '新建调查'}</button></div>
    {<>
      {offline && <div className="regression-demo-controls" aria-label="浏览器流程演示"><div><b>浏览器流程演示 · 无需连接</b><p>预设样例回放，当前不执行 pytest、不更新 SDK、不调用模型。连接服务可启动实际调查。</p></div><div className="toolbar-actions"><button className="button primary" onClick={playing ? () => setPlaying(false) : playDemo}>{playing ? <IconPlayerStop size={16}/> : <IconPlayerPlay size={16}/>} {playing ? '暂停演示' : demoStep === DEMO_STEPS.length - 1 ? '播放定位流程' : '继续演示'}</button><button className="button" disabled={demoStep === 0} onClick={() => {setPlaying(false);setDemoStep(i => Math.max(0, i - 1));}}>上一步</button><button className="button" disabled={demoStep === DEMO_STEPS.length - 1} onClick={() => {setPlaying(false);setDemoStep(i => Math.min(DEMO_STEPS.length - 1, i + 1));}}>下一步</button></div><label>演示阶段<select aria-label="演示阶段" value={demoStep} onChange={e => {setPlaying(false);setDemoStep(Number(e.target.value));setEvidence(null);setReport(null);}}>{DEMO_STEPS.map((step,i)=><option key={i} value={i}>{i+1}. {step[1]}</option>)}</select></label><p className="regression-demo-explanation">{DEMO_STEPS[demoStep][2]}</p></div>}
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div className="regression-context"><span className="regression-case-label">调查对象 <strong title={shownCatalog?.nodeid}>{shownCatalog?.nodeid?.split('::').at(-1) || '登记pytest case'}</strong></span><label>运行 ID<select aria-label="回归调查记录" value={record?.id || ''} onChange={e => setSelected(e.target.value)}>{!shownRecords.length && <option value="">尚无调查</option>}{shownRecords.map(r => <option key={r.id} value={r.id}>{offline ? '浏览器演示样例' : r.id.slice(-8)} · {r.spec.scenario} · {r.state}</option>)}</select></label><span className="regression-context-badge">{offline ? '浏览器预设回放' : 'SDK / AI 模拟 · CPU 实跑'}</span><span className="regression-context-note">{offline ? '未执行测试或模型调用' : 'SDK / AI 模拟 · CPU 实跑'}</span></div>
      {!offline && (configOpen || (!record && catalog)) && <div className="regression-config">
      <form className="regression-form" onSubmit={e => { e.preventDefault(); action('/regression/tasks', { config: { scenario, baseline, search_mode: mode, repeats: Number(repeat), max_experiments: Number(budget) }, idempotency_key: crypto.randomUUID(), ...(multiUser && profileId ? {profile_id:profileId} : {}) }); }}>
        <label>故障场景<select aria-label="回归故障场景" value={scenario} onChange={e => setScenario(e.target.value)}>{catalog?.scenarios.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>Baseline<select aria-label="回归Baseline" value={baseline} onChange={e => setBaseline(e.target.value)}>{catalog?.versions.slice(0, -1).map(v => <option key={v.id}>{v.id}</option>)}</select></label>
        <label>搜索精度<select aria-label="回归搜索精度" value={mode} onChange={e => setMode(e.target.value)}><option value="earliest_verified">严格确认最早失败</option><option value="boundary">二分边界（单调假设）</option></select></label>
        <label>重复次数<input aria-label="回归重复次数" type="number" min="1" max="5" value={repeat} onChange={e => setRepeat(e.target.value)}/></label>
        <label>实验预算<input aria-label="回归实验预算" type="number" min="1" max="200" value={budget} onChange={e => setBudget(e.target.value)}/></label>
        {multiUser && <label>我的AI配置<select aria-label="调查AI配置" value={profileId} onChange={e=>setProfileId(e.target.value)}><option value="">默认mock（未绑定个人配置）</option>{personalProfiles.filter(r=>r.enabled).map(r=><option key={r.id} value={r.id}>{r.name} · {r.config.model}</option>)}</select></label>}
        <button disabled={busy || !catalog} className="button primary"><IconPlayerPlay size={16}/>开始定位</button>
        <p>登记命令：<code>python -m pytest -q {catalog?.nodeid || 'test_regression.py::test_regression[fp16]'}</code> · mock-planner-v1 · 单worker · 独立HOME/缓存</p>
      </form>
      </div>}
      {record && <section aria-label="回归调查结果">
        <div className={`regression-hero ${hero.tone}`}>
          <div className="regression-hero-message">{hero.tone === 'supported' ? <IconCircleCheckFilled size={30}/> : hero.tone === 'running' ? <IconLoader2 size={30} className="spin"/> : <IconAlertCircle size={30}/>}<div><h2>{hero.title}</h2><p>{hero.description}</p>{!noRegression&&<small>{record.earliest_proven ? '已确认所选历史序列最早失败' : record.boundary ? '当前为已观测好坏范围，尚未证明最早失败' : `状态：${record.state}`} · 组件关联不代表源码根因</small>}</div></div>
          <div className={'regression-hero-facts'+(noRegression?' compact':'')}><div><span>最后通过 SDK</span><strong className="good">{record.boundary ? (record.boundary.good.date || shortSdk(record.boundary.good.id)) : view.latestOutcome === 'passed' ? shortSdk(record.target?.id) : view.baselineOutcome === 'passed' ? shortSdk(record.spec.baseline) : '未确认'}</strong></div>{!noRegression&&<><div><span>{record.earliest_proven ? '首次失败 SDK' : '已观测失败 SDK'}</span><strong className="bad">{record.boundary ? (record.boundary.bad.date || shortSdk(record.boundary.bad.id)) : view.latestOutcome === 'target_failure' ? shortSdk(record.target?.id) : '未确认'}</strong></div><div><span>关联组件</span><strong>{view.supported?.components.join(' + ') || '未确认'}</strong></div></>}</div>
          <div className="regression-hero-actions">{noRegression&&<button className="button" onClick={downloadBundle}><IconDownload size={16}/>证据包</button>}{offline && active(record) ? <button className="button" onClick={() => setPlaying(false)}>演示阶段 · {DEMO_STEPS[demoStep][1]}</button> : active(record) ? <button className="button" disabled={busy} onClick={() => action(`/regression/tasks/${record.id}/cancel`, {})}><IconPlayerStop size={16}/>取消调查</button> : <button className="button primary" onClick={downloadReport}><IconDownload size={16}/>下载调研报告</button>}<button className="button" onClick={() => copyText(issueSummary, 'summary')}>{copied === 'summary' ? <IconCheck size={16}/> : <IconCopy size={16}/>} {copied === 'summary' ? '已复制摘要' : '复制提单摘要'}</button>{!offline && !active(record) && record.state !== 'completed' && <button className="text-button" disabled={busy} onClick={() => action(`/regression/tasks/${record.id}/resume`, {})}><IconRefresh size={14}/>恢复调查</button>}</div>
        </div>
        {record.error && <div className="error-banner">{record.error.message}</div>}
        <ol className="regression-progress" aria-label="调查进度">{view.steps.map(step => <li className={step.state} key={step.label}>{step.state === 'done' ? <IconCircleCheckFilled size={26}/> : step.state === 'active' ? <IconLoader2 size={26} className="spin"/> : step.state === 'blocked' ? <IconAlertCircle size={26}/> : <IconCircle size={26}/>}<b>{step.label}</b><small>{step.detail}</small></li>)}</ol>
        <div className="regression-search-heading"><h2>{noRegression ? '环境验证' : '版本搜索'}</h2><span>{record.experiments.length} {offline ? '条示意记录' : '次实验'} · {offline ? '预设回放 · 非实测耗时' : `${record.elapsed_seconds.toFixed(1)}s`} · {record.spec.search_mode === 'earliest_verified' ? '严格首次确认' : '二分边界（单调假设）'}</span></div>
        <div className="regression-history" aria-label="版本搜索轨迹">{view.versions.filter(v => !noRegression || v.baseline || v.latest).map(v => <button key={v.id} className={`regression-version ${v.outcome} ${v.good ? 'boundary-good' : ''} ${v.bad ? 'boundary-bad' : ''}`} title={`${v.id} · ${v.experiments.length}次实验`} disabled={!v.experiments.length} onClick={() => inspect(v.experiments.at(-1).id)}>{v.baseline && <span className="regression-version-tag">基线</span>}{v.latest && <span className="regression-version-tag latest">最新</span>}<small>{v.date.slice(5)}</small><b>{outcomeLabel[v.outcome] || (v.outcome === 'untested' ? '未测' : '未完成')}</b>{(v.good || v.bad) && <span className="regression-boundary-caption">{v.good ? '最后通过' : record.earliest_proven ? '首次失败' : '观测失败'}</span>}</button>)}</div>
        <p className="regression-search-note">{record.earliest_proven ? `二分定位后补测更早版本，确认 ${shortSdk(record.boundary.bad.id)} 为所选历史序列首次失败。` : record.boundary ? '已验证的好坏范围见上方；缺失或未测版本不会补计通过。' : record.result === 'no_regression' ? '最新环境完整通过，未进入日期搜索和组件实验。' : '基线与最新环境校准通过后，才进入目标故障搜索。'}</p>
        {!noRegression && <div className="regression-investigation-grid"><section aria-label="搜索过程"><h3>搜索过程</h3><div className="regression-search-rounds">{view.rounds.map((round, index) => <button key={round.sdk} onClick={() => inspect(round.evidence.at(-1))}><span className="regression-round-index">{index + 1}</span><b>第 {index + 1} 轮</b><code>{shortSdk(round.sdk)}</code><span className={`regression-status ${round.outcome}`}>{outcomeLabel[round.outcome] || '未完成'}</span><small>{round.interval ? `范围 ${round.interval.map(shortSdk).join(' ～ ')}` : '区间待确认'}</small></button>)}{record.earliest_proven && <div className="regression-audit-row"><IconCircleCheckFilled size={22}/><b>审计</b><span>更早候选均通过，确认首次失败为 {shortSdk(record.boundary.bad.id)}</span></div>}{!view.rounds.length && <p className="regression-empty-note">{active(record) ? '正在校准端点，尚无二分实验。' : '本次未执行二分搜索，查看结论及原始实验。'}</p>}</div></section>
        <section aria-label="组件对照验证"><h3>组件对照验证</h3><div className="regression-table-scroll"><table className="regression-comparison"><thead><tr><th>实验</th><th>结果</th><th>解释</th></tr></thead><tbody>{(view.supported ? [view.supported] : record.attribution).flatMap(row => [<tr key={`${row.components}-forward`}><td>好 SDK + 新版 {row.components.join(' + ')}</td><td><span className={`regression-status ${row.forward}`}>{outcomeLabel[row.forward] || row.forward}</span></td><td>{row.forward === 'target_failure' ? '引入同一故障' : row.forward === 'passed' ? '未引入目标故障' : '尚无稳定证据'}</td></tr>, <tr key={`${row.components}-rollback`}><td>坏 SDK + 旧版 {row.components.join(' + ')}</td><td><span className={`regression-status ${row.rollback}`}>{outcomeLabel[row.rollback] || row.rollback}</span></td><td>{row.rollback === 'passed' ? '回退后恢复' : row.rollback === 'target_failure' ? '目标故障仍存在' : '尚无稳定证据'}</td></tr>])}</tbody></table></div>{view.supported ? <p className="regression-component-verdict"><b>双向支持：{view.supported.components.join(' + ')}（模拟组件）</b><span>仅支持所测 mock 场景的组件关联，不代表源码根因或唯一责任。</span></p> : <p className="regression-empty-note">{record.attribution.length ? '当前干预尚无双向支持，不能确认组件关联。' : '尚无组件干预证据，不推断组件归属。'}</p>}</section></div>}
        <div className="regression-disclosures"><details><summary><IconFileText size={17}/>{offline ? '演示实验与说明' : '原始实验与日志'} · {record.experiments.length} 条<IconChevronRight size={16}/></summary><div className="regression-table-scroll"><table className="regression-table"><thead><tr><th>实验</th><th>SDK / 组合</th><th>重复</th><th>结果</th><th>用时</th><th>证据</th></tr></thead><tbody>{record.experiments.map(e => <tr key={e.id}><td className="mono">{e.id}</td><td><code>{e.label}</code><small>{Object.entries(e.components).map(([k, v]) => `${k}=r${v}`).join(' · ')}</small></td><td>{e.repeat + 1}</td><td><span className={`regression-status ${e.classification}`}>{statuses[e.classification] || e.classification}</span></td><td>{offline ? '未实测' : e.finished_at ? `${(e.finished_at - e.started_at).toFixed(2)} s` : '执行中'}</td><td><button className="text-button" disabled={e.classification === 'pending'} onClick={() => inspect(e.id)}>查看日志</button></td></tr>)}</tbody></table><button className="text-button" onClick={() => downloadJson(`${record.id}.json`, record)}>导出原始JSON</button></div></details>
        <details><summary><IconFileText size={17}/>{offline ? `演示决策 · ${record.decisions.length} 条（未调用模型）` : `阶段与模型决策 · ${record.model_calls} 次`}<IconChevronRight size={16}/></summary><div className="regression-events">{record.events.map((e, i) => <p key={i}><b>{phases[e.phase] || e.phase}</b><span>{e.message}</span></p>)}{record.decisions.map((d, i) => <details key={i}><summary>Mock模型决策 · {d.candidate_id}</summary><pre>{JSON.stringify(d, null, 2)}</pre></details>)}</div></details></div>
        {!noRegression && <div className="regression-repro"><div><h3>最简复现</h3><small>{offline ? '浏览器回放不生成可执行复现命令。' : '重放无需模型，需保留冻结场景与环境。'}</small></div><code>{offline ? '连接服务后生成实际复现指令与证据' : record.experiments.some(e => e.classification === 'target_failure') ? (report?.markdown.split('```bash\n')[1]?.split('\n```')[0] || '完整固定场景命令生成后可复制') : '尚无目标失败实验可重放'}</code><button className="button" disabled={offline || active(record) || !record.experiments.some(e => e.classification === 'target_failure')} onClick={copyCommand}>{copied === 'command' ? <IconCheck size={16}/> : <IconCopy size={16}/>} {copied === 'command' ? '已复制命令' : '复制命令'}</button><button className="button" disabled={active(record)} onClick={downloadBundle}><IconDownload size={16}/>{offline ? '下载演示数据' : '下载证据包'}</button></div>}
        <button className="text-button regression-report-toggle" disabled={active(record)} onClick={viewReport}>报告预览<IconChevronDown size={14}/></button>
        {tab === 'report' && report && <div className="regression-report"><div className="toolbar-actions"><button className="button" onClick={() => downloadText(`${record.id}.md`, report.markdown)}>下载Markdown</button><button className="button" onClick={() => downloadText(`${record.id}.html`, report.html, 'text/html')}>下载HTML</button></div><pre>{report.markdown}</pre></div>}
        {evidence && <section className="regression-evidence" aria-label="回归实验证据"><div><h3>{evidence.id} · {offline ? '浏览器示意记录' : '原始pytest证据'}</h3><button className="text-button" onClick={() => setEvidence(null)}>关闭证据</button></div><p>退出码 {evidence.process?.returncode} · {evidence.classification} · SHA256 {evidence.environment_sha256}</p><pre>{evidence.process?.stdout || '暂无输出'}{evidence.process?.stderr}</pre><details><summary>{offline ? '样例组件组合（无实际加载观察）' : '原始阶段与环境观察'}</summary><pre>{JSON.stringify({ stages: evidence.stages, components: evidence.observed_components, source: evidence.source }, null, 2)}</pre></details></section>}
      </section>}
    </>}
  </div>;
}
