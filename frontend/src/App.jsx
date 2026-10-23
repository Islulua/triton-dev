import { useEffect, useRef, useState } from 'react';
import {
  IconHome, IconPackages, IconPlayerPlay, IconFileAnalytics, IconSettings,
  IconSearch, IconScale, IconPlus, IconX, IconCircleCheckFilled, IconCircleMinus,
  IconLock, IconChevronDown, IconChevronRight, IconDotsVertical, IconInfoCircle,
  IconCopy, IconDownload, IconRefresh, IconCheck, IconArrowRight, IconFlask,
  IconTerminal2, IconCircleXFilled, IconClock, IconFolder, IconShieldCheck,
  IconPlugConnected, IconAlertCircle, IconArrowLeft, IconMenu2, IconPlayerStop,
  IconSparkles, IconCircleFilled,
} from '@tabler/icons-react';
import { CASES, SDKS, DEMO_DATE, loadState, validateCombination, validateParams,
  combinationDiff, demoFailure, sdkLabel, tritonLabel, torchLabel, normalizeTask } from './model';
import { request, downloadJson } from './api';

const NAV = [ ['home', '工作台', IconHome], ['env', '环境与制品', IconPackages],
  ['runs', '用例与运行', IconPlayerPlay], ['diagnosis', '诊断与证据', IconFileAnalytics] ];
const STATUSES = {
  imported: ['导入通过', IconCircleCheckFilled, 'success'], unverified: ['未验证', IconCircleMinus, 'muted'],
  draft: ['草稿', IconCircleMinus, 'muted'], preparing: ['准备中', IconRefresh, 'progress'],
  passed: ['通过', IconCircleCheckFilled, 'success'], failed: ['失败', IconCircleXFilled, 'danger'],
  queued: ['排队中', IconClock, 'progress'], running: ['运行中', IconRefresh, 'progress'],
  cancelled: ['已取消', IconCircleMinus, 'muted'], interrupted: ['已中断', IconAlertCircle, 'warning'],
  timeout: ['超时', IconAlertCircle, 'warning'], error: ['执行错误', IconAlertCircle, 'danger'],
};
function Status({ value, children }) {
  const [label, Icon, color] = STATUSES[value] || STATUSES.unverified;
  return <span className={`status ${color}`}><Icon size={17} className={['running', 'preparing'].includes(value) ? 'spin' : ''} />{children || label}</span>;
}
function Button({ children, icon: Icon, primary, small, className = '', ...props }) {
  return <button className={`button ${primary ? 'primary' : ''} ${small ? 'small' : ''} ${className}`} {...props}>{Icon && <Icon size={small ? 16 : 19} stroke={1.7} />}{children}</button>;
}
function Field({ label, hint, children }) {
  return <label className="field"><span className="field-label">{label}</span>{children}{hint && <span className="field-hint">{hint}</span>}</label>;
}
function Select({ children, ...props }) { return <span className="select"><select {...props}>{children}</select><IconChevronDown size={17} /></span>; }
function Empty({ title, text, children }) { return <div className="empty"><IconFolder size={36} stroke={1.3} /><h3>{title}</h3><p>{text}</p>{children}</div>; }
function Info({ children, warning = false }) { return <div className={`info ${warning ? 'warning' : ''}`}><IconInfoCircle size={17} /><span>{children}</span></div>; }
function Tabs({ items, current, onChange }) {
  return <div className="tabs" role="tablist">{items.map(([id, name]) => <button key={id} role="tab" aria-selected={current === id} className={current === id ? 'active' : ''} onClick={() => onChange(id)}>{name}</button>)}</div>;
}
function Search({ value, onChange, placeholder }) {
  return <label className="search"><IconSearch size={20} stroke={1.7} /><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={e => onChange(e.target.value)} />{value && <button aria-label="清空搜索" onClick={() => onChange('')}><IconX size={16} /></button>}</label>;
}

export function App() {
  const [data, setData] = useState(() => loadState(window.localStorage));
  const [page, setPage] = useState('env');
  const [overlay, setOverlay] = useState(() => window.innerWidth <= 1000);
  const [envTab, setEnvTab] = useState('saved');
  const [runTab, setRunTab] = useState('cases');
  const [query, setQuery] = useState('');
  const [panel, setPanel] = useState('create');
  const [source, setSource] = useState('baseline');
  const [draft, setDraft] = useState({ name: 'trial-1023', sdk: '1023', triton: '1023', torch: '1022' });
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(['matmul']);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [runEnv, setRunEnv] = useState('baseline');
  const [runName, setRunName] = useState('correctness-check');
  const [params, setParams] = useState({ M: 128, N: 128 });
  const [timeout, setTimeoutValue] = useState(300);
  const [currentRun, setCurrentRun] = useState(null);
  const [detailTab, setDetailTab] = useState('result');
  const [currentCase, setCurrentCase] = useState('matmul');
  const [compareLeft, setCompareLeft] = useState('baseline');
  const [compareRight, setCompareRight] = useState('nightly-1023');
  const [diagnostic, setDiagnostic] = useState(null);
  const [assistant, setAssistant] = useState(false);
  const [rowMenu, setRowMenu] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [mode, setMode] = useState('demo');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [jobs, setJobs] = useState([]);
  const [apiRuns, setApiRuns] = useState([]);
  const [job, setJob] = useState('');
  const [events, setEvents] = useState([]);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const timers = useRef([]);
  const generation = useRef(0);
  const drawerRef = useRef(null);
  const activeRequests = useRef(new Set());
  const submissionKeys = useRef(new Map());
  const envs = data.environments;
  const runs = mode === 'local' ? apiRuns : data.runs;
  const activeRun = runs.find(r => r.id === currentRun);
  const sourceEnv = envs.find(e => e.name === source) || envs[0];

  useEffect(() => { try { window.localStorage.setItem('triton-dev-ui-v1', JSON.stringify(data)); } catch { /* Storage may be disabled. */ } }, [data]);
  useEffect(() => () => { timers.current.forEach(clearTimeout); generation.current += 1; }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 3600); return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    const media = window.matchMedia('(max-width:1000px)');
    const change = () => setOverlay(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    if (!panel || !overlay) return;
    const previous = document.activeElement;
    const focusable = () => [...(drawerRef.current?.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]') || [])].filter(el => el.getClientRects().length);
    focusable()[0]?.focus();
    const trap = e => {
      if (e.key !== 'Tab') return;
      const items = focusable(); const first = items[0]; const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', trap);
    return () => { window.removeEventListener('keydown', trap); if (previous?.isConnected) previous.focus(); };
  }, [panel, overlay]);
  useEffect(() => {
    setError('');
    function key(e) { if (e.key === 'Escape') { setPanel(null); setRowMenu(null); setMobileNav(false); } }
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  }, [panel]);
  useEffect(() => {
    if (!connected || mode !== 'local') return;
    let stopped = false;
    const controller = new AbortController();
    async function poll() {
      try {
        const records = await request('/tasks', { token, signal: controller.signal });
        if (!stopped) { setApiRuns(records.map(normalizeTask).reverse()); setConnectionError(''); }
      } catch (e) { if (!stopped && e.name !== 'AbortError') setConnectionError(e.message); }
    }
    poll(); const timer = setInterval(poll, 1500);
    return () => { stopped = true; controller.abort(); clearInterval(timer); };
  }, [connected, mode, token]);
  useEffect(() => {
    setEvents([]);
    if (mode !== 'local' || !connected || !currentRun) return;
    let stopped = false; let cursor = 0; const controller = new AbortController();
    async function pollEvents() {
      try {
        const response = await fetch(`/api/tasks/${encodeURIComponent(currentRun)}/events?after=${cursor}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal });
        if (!response.ok) throw new Error(`事件读取失败（${response.status}）`);
        const text = await response.text();
        const parsed = text.split('\n').filter(line => line.startsWith('data: ')).map(line => JSON.parse(line.slice(6)));
        if (!stopped && parsed.length) { cursor = Math.max(cursor, ...parsed.map(e => e.id)); setEvents(previous => [...previous, ...parsed]); }
      } catch (e) { if (!stopped && e.name !== 'AbortError') setConnectionError(e.message); }
    }
    pollEvents(); const timer = setInterval(pollEvents, 1500);
    return () => { stopped = true; controller.abort(); clearInterval(timer); };
  }, [mode, connected, currentRun, token]);

  function later(callback, ms) { timers.current.push(setTimeout(callback, ms)); }
  function navigate(next) { setPage(next); setPanel(null); setQuery(''); setRowMenu(null); setMobileNav(false); setError(''); if (next !== 'runs') setCurrentRun(null); }
  function openPanel(next) { setPanel(next); setError(''); setRowMenu(null); }
  function cloneFrom(env) { setSource(env.name); setDraft({ name: envs.some(e => e.name === 'trial-1023') ? `trial-${envs.length + 1}` : 'trial-1023', sdk: env.sdk, triton: env.triton, torch: env.torch }); openPanel('create'); }
  async function copy(text) { try { await navigator.clipboard.writeText(text); setToast('已复制到剪贴板'); } catch { setToast('浏览器未允许复制，请手动选择文本。'); } }
  function saveCombination(prepare) {
    const validation = validateCombination(draft, envs); if (validation) { setError(validation); return; }
    setError('');
    const name = draft.name;
    const environment = { ...draft, description: `基于 ${source} 创建`, python: sourceEnv.python, status: prepare ? 'preparing' : 'draft', date: DEMO_DATE, time: '刚刚' };
    setData(prev => ({ ...prev, environments: [...prev.environments, environment] }));
    if (!prepare) { setPanel(null); setToast('演示组合已保存，尚未执行准备或验证。'); return; }
    setBusy(true);
    later(() => {
      setData(prev => ({ ...prev, environments: prev.environments.map(e => e.name === name ? { ...e, status: 'imported' } : e) }));
      setBusy(false); setPanel(current => current === 'create' ? null : current); setToast('演示准备流程完成；未安装真实 SDK 或验证原生功能。');
    }, 1100);
  }
  function prepareEnvironment(environment) {
    setRowMenu(null);
    setData(prev => ({ ...prev, environments: prev.environments.map(e => e.name === environment.name ? { ...e, status: 'preparing' } : e) }));
    later(() => {
      setData(prev => ({ ...prev, environments: prev.environments.map(e => e.name === environment.name ? { ...e, status: 'imported' } : e) }));
      setToast('演示导入检查完成；没有安装或验证真实制品。');
    }, 900);
  }
  function startDemo({ ids = selected, environment = runEnv, parameters = params, parent = null } = {}) {
    if (!ids.length) { setError('请先选择至少一个用例。'); return; }
    const validation = validateParams(parameters); if (validation) { setError(validation); return; }
    if (!Number.isFinite(Number(timeout)) || Number(timeout) <= 0 || Number(timeout) > 3600) { setError('超时需为 1–3600 秒。'); return; }
    const snapshot = envs.find(e => e.name === environment);
    if (!snapshot || snapshot.status !== 'imported') { setError('请选择已完成演示导入检查的环境组合。'); return; }
    const id = `run_demo_${crypto.randomUUID().slice(0, 8)}`;
    const record = { id, name: runName.trim() || 'correctness-check', state: 'queued', env: environment,
      snapshot: { ...snapshot }, caseIds: [...ids], failedIds: [], params: { ...parameters }, parent,
      date: DEMO_DATE, time: '刚刚', elapsed: '—', source: 'demo' };
    setData(prev => ({ ...prev, runs: [record, ...prev.runs] }));
    setPanel(null); setPage('runs'); setRunTab('history'); setCurrentRun(id); setCurrentCase(ids[0]); setDetailTab('result');
    later(() => setData(prev => ({ ...prev, runs: prev.runs.map(r => r.id === id && r.state === 'queued' ? { ...r, state: 'running' } : r) })), 350);
    later(() => {
      const failedIds = demoFailure(ids, parameters);
      setData(prev => ({ ...prev, runs: prev.runs.map(r => r.id === id && ['queued', 'running'].includes(r.state)
        ? { ...r, state: failedIds.length ? 'failed' : 'passed', failedIds, elapsed: '2.1s' } : r) }));
    }, 2100);
  }
  async function connect() {
    if (!token.trim()) { setConnectionError('请输入本地任务服务的访问令牌。'); return; }
    const attempt = ++generation.current;
    setConnectionBusy(true); setConnectionError('');
    try {
      const [registered, records] = await Promise.all([request('/jobs', { token }), request('/tasks', { token })]);
      if (attempt !== generation.current) return;
      setJobs(registered); setJob(registered[0]?.job_id || ''); setApiRuns(records.map(normalizeTask).reverse());
      setConnected(true); setMode('local'); setToast('本地任务 API 已连接。环境与用例设计仍使用演示数据。');
    } catch (e) { if (attempt === generation.current) { setConnectionError(e.message); setConnected(false); } }
    finally { setConnectionBusy(false); }
  }
  async function submitApi(jobId = job) {
    if (!jobId || busy || activeRequests.current.has(jobId)) return;
    activeRequests.current.add(jobId); setBusy(true); setError('');
    const idempotencyKey = submissionKeys.current.get(jobId) || crypto.randomUUID();
    submissionKeys.current.set(jobId, idempotencyKey);
    try {
      const record = await request('/tasks', { token, method: 'POST', body: { job_id: jobId, idempotency_key: idempotencyKey } });
      submissionKeys.current.delete(jobId);
      setApiRuns(prev => [normalizeTask(record), ...prev.filter(r => r.id !== record.id)]);
      setPage('runs'); setRunTab('history'); setCurrentRun(record.id); setDetailTab('result'); setPanel(null);
    } catch (e) { setError(e.message); }
    finally { activeRequests.current.delete(jobId); setBusy(false); }
  }
  async function cancelRun(run) {
    if (run.source === 'api') {
      try { const updated = await request(`/tasks/${encodeURIComponent(run.id)}/cancel`, { token, method: 'POST', body: {} }); setApiRuns(prev => prev.map(r => r.id === run.id ? normalizeTask(updated) : r)); setToast('已请求取消，等待进程结束。'); }
      catch (e) { setToast(e.message); }
    } else { setData(prev => ({ ...prev, runs: prev.runs.map(r => r.id === run.id ? { ...r, state: 'cancelled', elapsed: '—' } : r) })); setToast('演示运行已取消，原记录已保留。'); }
  }
  function rerunFailed(run) {
    if (!run.failedIds.length) return;
    startDemo({ ids: run.failedIds, environment: run.env, parameters: run.params, parent: run.id });
  }
  function exportRun(run) {
    downloadJson(`triton-dev-${run.id}.json`, run.source === 'api' ? { source: 'local-task-api', record: run.record, events }
      : { schema_version: 1, source: 'browser-demo', native_verification: 'not_checked', run });
    setToast(run.source === 'api' ? '已导出任务记录 JSON；不是后端完整证据 ZIP。' : '已导出演示记录 JSON，包含明确的演示来源。');
  }
  function openRun(run) { setCurrentRun(run.id); setPage('runs'); setRunTab('history'); setPanel(null); setDetailTab('result'); setCurrentCase(run.failedIds[0] || run.caseIds[0] || ''); }
  function runDiagnosis() {
    if (compareLeft === compareRight) { setError('基线和候选必须是不同组合。'); return; }
    setBusy(true); setError('');
    later(() => { setDiagnostic({ good: compareLeft, bad: compareRight, source: 'browser-demo', scope: 'sdk_combination',
      conclusion: '组合变化关联，最终归属未确认', observations: [ ['good-1', '通过'], ['good-2', '通过'], ['bad-1', '目标故障'], ['bad-2', '目标故障'] ] }); setBusy(false); }, 900);
  }
  const filteredEnvs = envs.filter(e => `${e.name} ${e.description} ${sdkLabel(e.sdk)}`.toLowerCase().includes(query.toLowerCase()));
  const filteredCases = CASES.filter(c => (!onlyFailed || c.result === 'failed') && `${c.name} ${c.tag} ${c.params}`.toLowerCase().includes(query.toLowerCase()));
  const filteredRuns = runs.filter(r => `${r.id} ${r.name} ${r.env}`.toLowerCase().includes(query.toLowerCase()));
  const toggleCase = id => setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  const heading = { home: ['工作台', '从明确的环境组合开始，完成一次可复现的验证。'], env: ['环境与制品', '每次运行绑定明确的版本组合。'],
    runs: ['用例与运行', '选择用例、查看执行现场，并保留每一次复测。'], diagnosis: ['诊断与证据', '让判断有依据，让复现可以移交。'], settings: ['设置', '管理本地连接与界面偏好。'] }[page];

  return <div className={`app ${panel ? 'has-drawer' : ''}`}>
    <aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`} aria-label="主导航" inert={overlay && !!panel}>
      <a className="brand" href="#env" onClick={e => { e.preventDefault(); navigate('env'); }}><img src="/assets/brand-mark.png" alt="" /><span>triton-dev</span></a>
      <nav>{NAV.map(([id, label, Icon]) => <button key={id} className={page === id ? 'nav-item active' : 'nav-item'} aria-current={page === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon size={23} stroke={1.65} />{label}</button>)}</nav>
      <button className={`nav-item settings-nav ${page === 'settings' ? 'active' : ''}`} onClick={() => navigate('settings')}><IconSettings size={24} stroke={1.65} />设置</button>
    </aside>
    <header className="topbar" inert={overlay && !!panel}>
      <button className="icon-button mobile-toggle" aria-label="打开导航" onClick={() => setMobileNav(!mobileNav)}><IconMenu2 size={22} /></button>
      <button className="connection-pill" onClick={() => navigate('settings')}><IconCircleFilled size={11} className={connected ? 'success' : 'muted'} />{connected ? '本地 API 已连接' : '本地预览'}<span className="connection-target">· {connected ? '127.0.0.1' : '未连接服务'}</span></button>
      <div className="topbar-right"><span>{DEMO_DATE}</span><span className="topbar-divider" /><button className={`mode-pill ${mode === 'local' ? 'live' : ''}`} onClick={() => navigate('settings')}>{mode === 'local' ? '任务 API 模式' : '演示数据'}</button></div>
    </header>
    <div className="workspace">
      <main className="main-content" id="main" inert={overlay && !!panel}>
        {!(page === 'runs' && activeRun) && <div className="page-heading"><h1>{heading[0]}</h1><p>{heading[1]}</p></div>}
        {mode === 'local' && ['env', 'home', 'diagnosis'].includes(page) && <Info warning>仅任务接口已接入本地服务。本页环境与诊断仍为界面演示，不会安装或修改真实制品。</Info>}
        {connectionError && mode === 'local' && <div className="error-banner" role="alert"><IconAlertCircle size={18} />{connectionError}<button onClick={() => navigate('settings')}>检查连接</button></div>}

        {page === 'env' && <>
          <div className="section-toolbar"><Tabs items={[[ 'saved', '已保存组合' ], [ 'sdks', 'SDK 制品' ]]} current={envTab} onChange={setEnvTab} /><div className="toolbar-actions"><Button icon={IconScale} onClick={() => openPanel('compare')}>比较版本</Button>{!panel && <Button primary icon={IconPlus} onClick={() => cloneFrom(sourceEnv)}>创建组合</Button>}</div></div>
          <Search value={query} onChange={setQuery} placeholder={envTab === 'saved' ? '搜索组合名称、SDK 版本或备注…' : '搜索 SDK 版本或日期…'} />
          {envTab === 'saved' ? <div className="table-scroll"><table className="data-table environment-table"><thead><tr><th>组合</th><th>基础 SDK</th><th>Python</th><th>验证状态</th><th>更新时间</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{filteredEnvs.map(env => <tr key={env.name} className={source === env.name ? 'selected-row' : ''}><td><button className="row-name" onClick={() => { setSource(env.name); openPanel('inspect'); }}>{env.name}</button><span className="secondary-line">{env.description}</span></td><td className="sdk-cell">{sdkLabel(env.sdk)}</td><td>{env.python}</td><td><Status value={env.status}>{env.name === 'baseline' && env.status === 'imported' ? '已安装' : undefined}</Status>{env.name === 'baseline' && env.status === 'imported' && <span className="secondary-line indent-status">导入通过</span>}</td><td><span>{env.date}</span><span className="secondary-line">{env.time}</span></td><td className="menu-cell"><button aria-label={`${env.name} 更多操作`} className="icon-button" onClick={() => setRowMenu(rowMenu === env.name ? null : env.name)}><IconDotsVertical size={19} /></button>{rowMenu === env.name && <div className="row-menu">{!['imported', 'preparing'].includes(env.status) && <button onClick={() => prepareEnvironment(env)}><IconRefresh size={16} />准备并检查导入</button>}<button onClick={() => cloneFrom(env)}><IconCopy size={16} />基于此组合创建</button><button onClick={() => { setSource(env.name); openPanel('inspect'); setRowMenu(null); }}><IconInfoCircle size={16} />查看组合快照</button><button onClick={() => { setRunEnv(env.name); openPanel('run'); }}><IconPlayerPlay size={16} />用于一次运行</button></div>}</td></tr>)}</tbody></table>{!filteredEnvs.length && <Empty title="没有匹配的组合" text="试试其他名称、版本或备注。"><Button onClick={() => setQuery('')}>清空搜索</Button></Empty>}</div>
          : <div className="table-scroll"><table className="data-table"><thead><tr><th>SDK 制品</th><th>大小</th><th>哈希摘要</th><th>来源</th><th>操作</th></tr></thead><tbody>{SDKS.filter(s => s.label.includes(query)).map(sdk => <tr key={sdk.id}><td><strong>{sdk.label}</strong><span className="secondary-line">Python {sdk.python} · wheel / lib / bin</span></td><td>{sdk.size}</td><td className="mono">{sdk.sha}</td><td><span className="subtle-badge">{sdk.source}</span></td><td><Button small onClick={() => { setDraft(prev => ({ ...prev, sdk: sdk.id, triton: sdk.id, torch: sdk.id })); openPanel('create'); }}>创建组合</Button></td></tr>)}</tbody></table></div>}
        </>}

        {page === 'home' && <div className="home-body"><div className="welcome-line"><IconFlask size={34} stroke={1.35} /><div><h2>从一个稳定基线开始</h2><p>把环境、输入和结果放在同一条可追溯的工作流里。</p></div></div><div className="workflow-steps">{[['01', '选择环境', '使用已保存的不可变组合', 'env'], ['02', '选择用例', '按名称、标签和参数筛选', 'cases'], ['03', '查看结果', '复测失败项，保留原始现场', 'history']].map(([number, title, text, target]) => <button key={number} onClick={() => { if (target === 'env') navigate('env'); else { navigate('runs'); setRunTab(target); } }}><span className="step-number">{number}</span><h3>{title}</h3><p>{text}</p><IconArrowRight size={20} /></button>)}</div><div className="section-title"><h2>最近运行</h2><button className="text-button" onClick={() => { navigate('runs'); setRunTab('history'); }}>查看全部<IconChevronRight size={16} /></button></div>{renderRuns(runs.slice(0, 4))}<Info>环境组合不会改变你的终端。每次提交都会记录所选环境及运行参数。</Info></div>}

        {page === 'runs' && !activeRun && <>
          <div className="section-toolbar"><Tabs items={[[ 'cases', '用例库' ], [ 'history', '运行记录' ]]} current={runTab} onChange={id => { setRunTab(id); setQuery(''); }} /><Button primary icon={IconPlayerPlay} onClick={() => openPanel('run')}>{mode === 'local' ? '提交登记任务' : '新建运行'}</Button></div>
          <div className="search-toolbar"><Search value={query} onChange={setQuery} placeholder={runTab === 'cases' ? '搜索用例、标签或参数…' : '搜索运行 ID、名称或环境…'} />{runTab === 'cases' && <button className={`filter-button ${onlyFailed ? 'active' : ''}`} aria-pressed={onlyFailed} onClick={() => setOnlyFailed(!onlyFailed)}>最近失败</button>}</div>
          {runTab === 'cases' ? <><Info>用例库为演示数据。连接服务后只能提交预先登记的任务，网页不会生成自由执行命令。</Info><div className="table-scroll"><table className="data-table case-table"><thead><tr><th><input type="checkbox" aria-label="选择全部可见用例" checked={filteredCases.length > 0 && filteredCases.every(c => selected.includes(c.id))} onChange={e => setSelected(e.target.checked ? [...new Set([...selected, ...filteredCases.map(c => c.id)])] : selected.filter(id => !filteredCases.some(c => c.id === id)))} /></th><th>用例</th><th>参数摘要</th><th>最近结果</th><th>操作</th></tr></thead><tbody>{filteredCases.map(c => <tr key={c.id} className={selected.includes(c.id) ? 'selected-row' : ''}><td><input type="checkbox" aria-label={`选择 ${c.name}`} checked={selected.includes(c.id)} onChange={() => toggleCase(c.id)} /></td><td><button className="row-name mono" onClick={() => { setCurrentCase(c.id); openPanel('case'); }}>{c.name}</button><span className="secondary-line">{c.tag}</span></td><td className="muted">{c.params}</td><td><Status value={c.result} /></td><td><button className="text-button" onClick={() => { setCurrentCase(c.id); openPanel('case'); }}>详情<IconChevronRight size={15} /></button></td></tr>)}</tbody></table>{!filteredCases.length && <Empty title="没有匹配的用例" text="修改搜索词或关闭“最近失败”筛选。" />}</div><div className="selection-footer"><strong>已选择 {selected.length} 项</strong><button className="text-button" onClick={() => setSelected([])}>清除选择</button><span>参数变更只应用于下一次运行</span></div></> : renderRuns(filteredRuns)}
        </>}

        {page === 'runs' && activeRun && renderRunDetail(activeRun)}

        {page === 'diagnosis' && <div className="diagnosis-body"><Info>诊断先验证目标故障是否复现，再比较环境变化。组件和团队归属需要额外证据。</Info><div className="section-title"><h2>版本对照</h2><span className="subtle-badge">界面演示</span></div><div className="comparison-form"><Field label="通过基线"><Select value={compareLeft} onChange={e => setCompareLeft(e.target.value)}>{envs.map(e => <option key={e.name}>{e.name}</option>)}</Select></Field><IconArrowRight size={23} className="compare-arrow" /><Field label="候选组合"><Select value={compareRight} onChange={e => setCompareRight(e.target.value)}>{envs.map(e => <option key={e.name}>{e.name}</option>)}</Select></Field></div><Field label="目标故障判据" hint="判据在实验前固定，不以任意失败代替目标故障。"><input value="call 阶段失败，日志包含 AssertionError" readOnly /></Field>{error && <p className="field-error" role="alert">{error}</p>}<Button primary icon={busy ? IconRefresh : IconPlayerPlay} disabled={busy || mode === 'local'} onClick={runDiagnosis}>{busy ? '生成演示观察…' : '运行演示对照'}</Button><p className="muted tiny">固定演示：基线 2 次通过、候选 2 次目标故障；不会执行后端实验。</p>{diagnostic && <div className="diagnostic-result"><h2>组合变化关联，最终归属未确认</h2><p>仅依据当前演示观察；尚不能推断 LLVM、cmodel 或 Triton 的缺陷归属。</p><table className="data-table"><thead><tr><th>观察 ID</th><th>环境组合</th><th>判据结果</th></tr></thead><tbody>{diagnostic.observations.map(([id, label]) => <tr key={id}><td className="mono">{id}</td><td>{id.startsWith('good') ? diagnostic.good : diagnostic.bad}</td><td><Status value={id.startsWith('good') ? 'passed' : 'failed'}>{label}</Status></td></tr>)}</tbody></table><Button icon={IconDownload} onClick={() => downloadJson('triton-dev-demo-diagnosis.json', diagnostic)}>导出演示对照报告</Button></div>}<button className="assistant-toggle" aria-expanded={assistant} onClick={() => setAssistant(!assistant)}><IconSparkles size={20} /><span>诊断助手<span className="muted"> · 脚本模型</span></span><IconChevronDown size={17} /></button>{assistant && <div className="assistant-body"><p>尚未接入实时 AI。建议先确认基线仍通过，再逐个替换支持独立切换的组件。</p><p className="muted">CLI 已提供受预算约束的脚本工作流；界面不会从日志推断未经验证的责任方。</p><Button small icon={IconCopy} onClick={() => copy('triton-dev agent workflow workflow.json --checkpoint state.json')}>复制工作流命令</Button></div>}</div>}

        {page === 'settings' && <div className="settings-body"><h2>运行模式</h2><div className="mode-options"><button className={mode === 'demo' ? 'selected' : ''} onClick={() => { generation.current += 1; setMode('demo'); setConnected(false); setToken(''); setConnectionError(''); setApiRuns([]); setEvents([]); setCurrentRun(null); }}><IconFlask size={23} /><span><strong>离线演示</strong><small>在浏览器中体验完整流程，不修改真实环境。</small></span>{mode === 'demo' && <IconCheck size={20} />}</button><button className={mode === 'local' ? 'selected' : ''} onClick={() => document.getElementById('api-token')?.focus()}><IconPlugConnected size={23} /><span><strong>本地任务 API</strong><small>读取登记任务，真实提交、取消并跟踪执行状态。</small></span>{mode === 'local' && <IconCheck size={20} />}</button></div><div className="settings-section"><h2>本地服务连接</h2><p>使用同源 <code>/api</code>。访问令牌仅保存在当前页面内存，刷新后需重新输入。</p><Field label="访问令牌"><input id="api-token" type="password" autoComplete="off" placeholder="输入 TRITON_DEV_SERVER_TOKEN" value={token} onChange={e => { setToken(e.target.value); if (connected) { setConnected(false); setMode('demo'); setApiRuns([]); } }} /></Field>{connectionError && <p role="alert" className="field-error">{connectionError}</p>}<Button primary icon={IconPlugConnected} disabled={connectionBusy || connected} onClick={connect}>{connectionBusy ? '正在连接…' : connected ? '已连接本地任务 API' : '连接并读取任务'}</Button>{connected && <Button className="disconnect" onClick={() => { setConnected(false); setMode('demo'); setToken(''); setApiRuns([]); setCurrentRun(null); }}>断开连接</Button>}<Info>环境组合、用例收集和诊断尚未暴露为 HTTP 接口。这些页面始终标注为演示。</Info><details><summary>如何启动本地服务</summary><pre className="command-block">triton-dev serve --jobs jobs.json \\{ '\n' }  --ui frontend/dist/client --port 8765</pre><p className="tiny muted">先配置访问令牌，再启动服务。开发预览通过本地代理访问同一 API。</p></details></div><div className="settings-section"><h2>演示记录</h2><p>组合和演示运行保存在本浏览器，真实任务记录由后端管理。</p><Button icon={IconDownload} onClick={() => downloadJson('triton-dev-browser-demo.json', { source: 'browser-demo', ...data })}>导出演示数据</Button></div></div>}

        <footer className="page-footer"><span><IconInfoCircle size={17} />原生加载与设备功能：未验证</span><span>仅用于开发与测试{mode === 'demo' ? '，当前为演示数据' : ' · 任务操作来自本地 API'}</span></footer>
      </main>
      {panel && <aside className="drawer" role="dialog" aria-modal={overlay ? "true" : "false"} aria-label={panel === 'create' ? '创建组合' : panel === 'compare' ? '比较版本' : panel === 'run' ? '新建运行' : '查看详情'} ref={drawerRef}>
        <div className="drawer-heading"><h2>{{ create: '创建组合', compare: '比较版本', inspect: '组合快照', run: mode === 'local' ? '提交登记任务' : '新建运行', case: '用例详情' }[panel]}</h2><button className="icon-button" aria-label="关闭侧栏" onClick={() => setPanel(null)}><IconX size={23} stroke={1.5} /></button></div>
        {panel === 'create' && <><div className="drawer-scroll"><div className="drawer-intro"><p>基于 {source} 创建一个新环境组合，<br />修改版本后进行独立验证。</p><Status value="unverified" /></div><Field label="来源组合"><span className="locked-input">{source}（{sdkLabel(sourceEnv.sdk)}）<IconLock size={16} /></span></Field><Field label="组合名称" hint="用于标识该版本组合，便于后续对比与复现。"><input value={draft.name} disabled={busy} onChange={e => setDraft({ ...draft, name: e.target.value })} /></Field><Field label="基础 SDK" hint="选择 Triton 编译器 SDK 的基础版本。"><Select value={draft.sdk} disabled={busy} onChange={e => setDraft({ ...draft, sdk: e.target.value })}>{SDKS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</Select></Field><Field label="Triton wheel" hint={draft.triton !== sourceEnv.triton ? '相对来源组合已修改的版本。' : '与来源组合保持一致。'}><Select value={draft.triton} disabled={busy} className={draft.triton !== sourceEnv.triton ? 'changed-input' : ''} onChange={e => setDraft({ ...draft, triton: e.target.value })}>{SDKS.map(s => <option key={s.id} value={s.id}>{tritonLabel(s.id)}</option>)}</Select></Field><Field label="Torch wheel" hint={draft.torch !== sourceEnv.torch ? '相对来源组合已修改的版本。' : '与来源组合保持一致。'}><Select value={draft.torch} disabled={busy} onChange={e => setDraft({ ...draft, torch: e.target.value })}>{SDKS.map(s => <option key={s.id} value={s.id}>{torchLabel(s.id)}</option>)}</Select></Field><div className="native-section"><Field label="原生组件" hint="当前随基础 SDK 提供的 cmodel 版本。"><input value="cmodel（跟随基础 SDK）" disabled /></Field><Info>原生混用尚未接入。</Info></div>{error && <p className="field-error" role="alert">{error}</p>}{busy && <Info>正在演示准备与导入检查，不会安装实际制品。</Info>}</div><div className="drawer-actions"><button className="text-button" disabled={busy} onClick={() => saveCombination(false)}>保存草稿</button><Button primary disabled={busy} icon={busy ? IconRefresh : undefined} onClick={() => saveCombination(true)}>{busy ? '演示准备中…' : '准备并验证'}</Button></div></>}
        {panel === 'compare' && <div className="drawer-scroll"><p className="muted drawer-description">只对比明确的版本来源，不推断兼容性或问题归属。</p><Field label="基线组合"><Select value={compareLeft} onChange={e => setCompareLeft(e.target.value)}>{envs.map(e => <option key={e.name}>{e.name}</option>)}</Select></Field><Field label="候选组合"><Select value={compareRight} onChange={e => setCompareRight(e.target.value)}>{envs.map(e => <option key={e.name}>{e.name}</option>)}</Select></Field><div className="diff-list">{combinationDiff(envs.find(e => e.name === compareLeft) || envs[0], envs.find(e => e.name === compareRight) || envs[0]).map(d => <div className={d.changed ? 'changed-diff' : ''} key={d.field}><strong>{d.field}</strong><span>{d.left}<IconArrowRight size={16} />{d.right}</span><small>{d.changed ? '版本来源已变化' : '保持一致'}</small></div>)}</div><Info>原生组件边界未知，暂不进行文件归属判断。</Info><Button icon={IconFileAnalytics} onClick={() => { navigate('diagnosis'); }}>进入版本对照</Button></div>}
        {panel === 'inspect' && <div className="drawer-scroll"><h3 className="snapshot-name">{sourceEnv.name}</h3><Status value={sourceEnv.status} /><dl className="key-values"><dt>基础 SDK</dt><dd>{sdkLabel(sourceEnv.sdk)}</dd><dt>Python</dt><dd>{sourceEnv.python}</dd><dt>Triton wheel</dt><dd>{tritonLabel(sourceEnv.triton)}</dd><dt>Torch wheel</dt><dd>{torchLabel(sourceEnv.torch)}</dd><dt>原生功能</dt><dd>未验证</dd><dt>数据来源</dt><dd>浏览器演示</dd></dl><Info>组合不可覆盖。创建新组合以保留版本变化记录。</Info><Button primary icon={IconCopy} onClick={() => cloneFrom(sourceEnv)}>基于此组合创建</Button><Button className="drawer-secondary" icon={IconTerminal2} onClick={() => copy(`triton-dev env exec --saved ${sourceEnv.name} -- python -m pytest tests/smoke`)}>复制 CLI 命令</Button><p className="tiny muted">演示名称未自动保存到 CLI 缓存，使用前需在 CLI 创建对应组合。</p></div>}
        {panel === 'case' && <div className="drawer-scroll"><h3 className="mono case-heading">{CASES.find(c => c.id === currentCase)?.name}</h3><dl className="key-values"><dt>参数摘要</dt><dd>{CASES.find(c => c.id === currentCase)?.params}</dd><dt>Fixtures</dt><dd>{CASES.find(c => c.id === currentCase)?.fixture}</dd><dt>文件</dt><dd className="mono">tests/tx82/test_correctness.py</dd><dt>数据来源</dt><dd>演示用例</dd></dl><Info>参数调整在新建运行中完成，不直接改写测试源码。</Info><Button primary icon={IconPlayerPlay} onClick={() => { setSelected([currentCase]); openPanel('run'); }}>运行此用例</Button></div>}
        {panel === 'run' && <><div className="drawer-scroll"><p className="muted drawer-description">{mode === 'local' ? '只能执行服务预先登记的任务。不会接收任意命令或修改任务参数。' : '运行环境和参数将留档，不会改变终端或已有记录。'}</p>{mode === 'local' ? <><Field label="已登记任务"><Select value={job} onChange={e => setJob(e.target.value)}>{jobs.length ? jobs.map(j => <option key={j.job_id}>{j.job_id}</option>) : <option value="">没有可用任务</option>}</Select></Field><Info>该操作会在本地后端真实执行。</Info></> : <><Field label="运行名称"><input value={runName} onChange={e => setRunName(e.target.value)} /></Field><Field label="环境组合"><Select value={runEnv} onChange={e => setRunEnv(e.target.value)}>{envs.map(e => <option key={e.name} value={e.name} disabled={e.status !== 'imported'}>{e.name}{e.status !== 'imported' ? '（尚未准备）' : ''}</option>)}</Select></Field><Field label="已选择用例"><span className="locked-input">{selected.length} 项用例<IconLock size={16} /></span></Field><div className="selected-case-chips">{selected.map(id => <span key={id}>{CASES.find(c => c.id === id)?.name}<button aria-label={`移除 ${id}`} onClick={() => toggleCase(id)}><IconX size={13} /></button></span>)}</div><div className="parameter-fields"><Field label="M"><input type="number" min="1" max="16384" value={params.M} onChange={e => setParams({ ...params, M: e.target.value })} /></Field><Field label="N"><input type="number" min="1" max="16384" value={params.N} onChange={e => setParams({ ...params, N: e.target.value })} /></Field></div><Field label="运行超时（秒）"><input type="number" min="1" max="3600" value={timeout} onChange={e => setTimeoutValue(e.target.value)} /></Field><Info>演示规则：matmul 在 M ≥ 128 时模拟数值失败。修改参数将创建新的运行记录。</Info></>}{error && <p className="field-error" role="alert">{error}</p>}</div><div className="drawer-actions"><button className="text-button" onClick={() => setPanel(null)}>取消</button><Button primary icon={IconPlayerPlay} disabled={busy || (mode === 'local' ? !connected || !job : !selected.length)} onClick={() => mode === 'local' ? submitApi() : startDemo()}>{mode === 'local' ? busy ? '正在提交…' : '提交登记任务' : '提交演示运行'}</Button></div></>}
      </aside>}
    </div>
    {toast && <div className="toast" role="status"><IconCircleCheckFilled size={18} />{toast}<button aria-label="关闭提示" onClick={() => setToast('')}><IconX size={15} /></button></div>}
  </div>;

  function renderRuns(items) {
    if (!items.length) return <Empty title={query ? '没有匹配的运行' : '还没有运行记录'} text={mode === 'local' ? '提交一个已登记任务，执行结果会出现在这里。' : '选择环境与用例，开始第一次演示运行。'}><Button primary icon={IconPlayerPlay} onClick={() => openPanel('run')}>新建运行</Button></Empty>;
    return <div className="table-scroll"><table className="data-table runs-table"><thead><tr><th>运行</th><th>环境组合</th><th>用例</th><th>结果</th><th>时间</th><th>操作</th></tr></thead><tbody>{items.map(run => <tr key={run.id}><td><button className="row-name" onClick={() => openRun(run)}>{run.name}</button><span className="secondary-line mono">{run.id}</span></td><td>{run.env}<span className="secondary-line">{run.source === 'api' ? '真实登记任务' : '演示环境快照'}</span></td><td>{run.source === 'api' ? '登记配置' : `${run.caseIds.length} 项`}</td><td><Status value={run.state} />{run.failedIds.length > 0 && <span className="secondary-line indent-status">{run.failedIds.length} 项失败</span>}</td><td>{run.date}<span className="secondary-line">{run.time} · {run.elapsed}</span></td><td><button className="text-button" onClick={() => openRun(run)}>查看记录<IconChevronRight size={15} /></button></td></tr>)}</tbody></table></div>;
  }
  function renderRunDetail(run) {
    const isActive = ['queued', 'running'].includes(run.state);
    const fail = run.failedIds.includes(currentCase);
    const caseInfo = CASES.find(c => c.id === currentCase);
    const logs = run.source === 'api' ? `${run.record?.result?.stdout || ''}${run.record?.result?.stderr || ''}${run.record?.error ? `\n${run.record.error.code}: ${run.record.error.message}` : ''}`
      : `${run.id} · 浏览器演示，不是真实执行日志\n环境组合: ${run.env} / SDK ${run.snapshot?.sdk}\n输入: M=${run.params.M}, N=${run.params.N}\n\n${isActive ? '等待演示任务完成…' : fail ? 'E  AssertionError: 数值结果超出容差\nE  Mismatched elements: 37 / 16384\nE  Maximum absolute difference: 0.125\nE  First failing index: (31, 64)\n\n   source: browser-demo\n   native_verification: not_checked' : `状态: ${STATUSES[run.state]?.[0] || run.state}\n结果仅用于演示界面交互。`}`;
    return <div className="run-detail"><button className="back-link" onClick={() => setCurrentRun(null)}><IconArrowLeft size={17} />返回运行记录</button><div className="run-title-row"><div><h1>运行详情</h1><p>{run.name}<span>·</span>{run.env}<span>·</span><span className="mono">{run.id}</span></p></div><div className="toolbar-actions"><Status value={run.state} />{isActive ? <Button icon={IconPlayerStop} onClick={() => cancelRun(run)}>取消运行</Button> : run.source === 'demo' && run.failedIds.length > 0 && <Button primary icon={IconRefresh} onClick={() => rerunFailed(run)}>仅复测失败项</Button>}</div></div>{run.parent && <Info>本次复测来自 {run.parent}，原始记录完整保留。</Info>}{run.source === 'demo' && <Info>浏览器演示记录，未执行真实 kernel。环境、参数与结果均可用于体验流程。</Info>}<div className={`result-layout ${run.source === 'api' ? 'api-result' : ''}`}>{run.source === 'demo' && <div className="result-list"><h3>{run.caseIds.length} 个用例</h3>{run.caseIds.map(id => <button key={id} className={currentCase === id ? 'active' : ''} onClick={() => setCurrentCase(id)}><Status value={isActive ? run.state : run.failedIds.includes(id) ? 'failed' : run.state === 'cancelled' ? 'cancelled' : 'passed'} /><span className="mono">{CASES.find(c => c.id === id)?.name}</span></button>)}</div>}<div className="result-main"><h2 className="mono">{run.source === 'api' ? '登记任务结果' : caseInfo?.name}</h2><Tabs items={[[ 'result', '结果' ], [ 'logs', '日志' ], [ 'snapshot', '环境快照' ], [ 'evidence', '证据' ]]} current={detailTab} onChange={setDetailTab} />{detailTab === 'result' && <>{run.source === 'demo' ? <><div className={`failure-summary ${fail ? '' : 'neutral'}`}>{isActive ? '任务执行状态正在更新。' : fail ? 'AssertionError：数值结果超出容差' : `当前用例：${STATUSES[run.state]?.[0] || run.state}`}</div>{!isActive && !['cancelled', 'interrupted'].includes(run.state) && <div className="stage-timeline">{['setup', 'call', 'teardown'].map(stage => <div key={stage}><Status value={stage === 'call' && fail ? 'failed' : 'passed'} /><strong>{stage}</strong><span>{stage === 'call' && fail ? '失败' : '通过'}</span></div>)}</div>}<div className="section-title"><h3>关键证据</h3><span className="tiny muted">演示观察 · 未接入真实 backend</span></div><dl className="evidence-grid"><dt>输入 shape</dt><dd>[{run.params.M}, {run.params.N}]</dd><dt>dtype</dt><dd>fp16</dd><dt>比较器</dt><dd>assert_close</dd><dt>rtol / atol</dt><dd>0.01 / 0.001</dd><dt>最大绝对误差</dt><dd>{fail ? '0.125' : '—'}</dd><dt>首个失败坐标</dt><dd>{fail ? '[31, 64]' : '—'}</dd></dl></> : <><Info>结果来自本地任务 API。未收集到 pytest 阶段时，不推断阶段或数值结果。</Info><dl className="key-values"><dt>状态</dt><dd><Status value={run.state} /></dd><dt>原始退出码</dt><dd>{run.record?.result?.returncode ?? '尚未返回'}</dd><dt>工作目录</dt><dd>{run.record?.request?.cwd || '—'}</dd><dt>数据来源</dt><dd>本地登记任务</dd></dl><h3>状态事件</h3><ul className="event-list">{events.map(e => <li key={e.id}><span className="mono">#{e.id}</span>{e.type}<span>{new Date(e.time * 1000).toLocaleTimeString('zh-CN')}</span></li>)}</ul></>}<div className="section-title"><h3>日志片段</h3><button className="text-button" onClick={() => copy(logs)}><IconCopy size={16} />复制</button></div><pre className="log-view">{logs || '任务尚未返回日志。'}</pre></>}{detailTab === 'logs' && <><div className="section-title"><p className="muted">{run.source === 'api' ? '展示后端保留的有界日志尾部，完整范围以运行记录为准。' : '以下是明确标记的演示日志。'}</p><Button small icon={IconCopy} onClick={() => copy(logs)}>复制日志</Button></div><pre className="log-view expanded">{logs || '任务尚未返回日志。'}</pre></>}{detailTab === 'snapshot' && <><Info>快照随本次记录保存，不跟随当前编辑器选择变化。</Info><pre className="json-view">{JSON.stringify(run.source === 'api' ? run.record?.request : { source: 'browser-demo', environment: run.snapshot, parameters: run.params, native_loading: 'not_checked' }, null, 2)}</pre></>}{detailTab === 'evidence' && <div className="evidence-export"><IconShieldCheck size={36} stroke={1.4} /><h3>{run.source === 'api' ? '导出已返回的任务记录' : '导出带来源标记的演示记录'}</h3><p>网页导出 JSON，不等于 CLI 的脱敏证据 ZIP。分享前请检查日志中的敏感信息。</p><Button icon={IconDownload} onClick={() => exportRun(run)}>导出记录 JSON</Button><Button className="drawer-secondary" icon={IconCopy} onClick={() => copy('triton-dev runs export <CLI_RUN_ID> --output evidence.zip')}>复制 CLI 导出模板</Button><p className="tiny muted">Server tasks 和 CLI runs 使用独立记录目录，不能直接互换运行 ID。</p></div>}<div className="result-footer"><span>原始运行保留 · 复测将创建新记录</span><button className="text-button" onClick={() => exportRun(run)}><IconDownload size={17} />导出记录</button></div></div></div></div>;
  }
}
