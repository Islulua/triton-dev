import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { IconActivity, IconDownload, IconPlayerPlay, IconInfoCircle } from '@tabler/icons-react';
import { request, downloadJson } from './api';
import preview from './profiling-preview.json';
import './profiling.css';
import { anchoredTimelineScroll, timelineShortcut } from './timeline-navigation';
const fmt = (n, digits = 2) => Number(n).toLocaleString('en-US', { maximumFractionDigits: digits });
const categories = { host: 'Host 调度', transfer: '数据传输', kernel: 'Device kernel', sync: 'Fence 信号', wait: 'Host 等待' };
const engineClass = e => e.track.startsWith('Matrix') ? 'matrix' : e.track.startsWith('Vector') ? 'vector' : e.track.startsWith('SDMA') ? 'sdma' : e.category;
function Metric({ title, value, unit, note }) { return <div className="profile-metric" title={note}><span>{title}</span><strong>{value}<small>{unit}</small></strong><span className="sr-only">{note}</span></div>; }
function Samples({ samples }) {
  const values = samples.map(s => s.device_us), low = Math.min(...values) * .96, high = Math.max(...values) * 1.04;
  const y = v => 146 - (v - low) / (high - low) * 114;
  return <svg viewBox="0 0 520 185" role="img" aria-label={`${values.length}次模拟采样，设备耗时最小${fmt(Math.min(...values))}微秒，最大${fmt(Math.max(...values))}微秒`}>
    {[0, .5, 1].map(n => <g key={n}><line x1="62" x2="500" y1={32 + n * 114} y2={32 + n * 114} stroke="#e5edef"/><text x="4" y={36 + n * 114}>{fmt(high - n * (high - low), 1)} μs</text></g>)}
    <polyline points={values.map((v, i) => `${62 + i / Math.max(1, values.length - 1) * 438},${y(v)}`).join(' ')} fill="none" stroke="#16877e" strokeWidth="2.5"/>
    {values.map((v, i) => <circle key={i} cx={62 + i / Math.max(1, values.length - 1) * 438} cy={y(v)} r="3" fill="#16877e"><title>采样 {i + 1}：{fmt(v)} μs</title></circle>)}
    <text x="62" y="176">采样 1</text><text x="445" y="176">采样 {values.length}</text>
  </svg>;
}
function Roofline({ report }) {
  const { summary: s, capture: { device } } = report;
  const x = v => 50 + (Math.log10(Math.max(.1, Math.min(10000, v))) + 1) / 5 * 440;
  const y = v => 150 - (Math.log10(Math.max(.01, v)) + 2) / 5 * 122;
  const ridge = device.peak_tflops * 1000 / device.peak_bandwidth_gbs;
  return <><svg viewBox="0 0 520 190" role="img" aria-label={`假设Roofline模型，有效算力${fmt(s.tflops)}TFLOP/s，上界${fmt(s.roof_tflops)}TFLOP/s，双对数坐标`}>
    {[.1, 1, 10, 100, 1000, 10000].map(v => <g key={v}><line x1={x(v)} x2={x(v)} y1="28" y2="150" stroke="#edf1f3"/><text x={x(v)} y="173" textAnchor="middle">{v >= 1000 ? `${v / 1000}k` : v}</text></g>)}
    {[.01, 1, 100].map(v => <text key={v} x="3" y={y(v) + 3}>{v}</text>)}
    <polyline points={`${x(.1)},${y(.1 * device.peak_bandwidth_gbs / 1000)} ${x(ridge)},${y(device.peak_tflops)} ${x(10000)},${y(device.peak_tflops)}`} fill="none" stroke="#a7bbc7" strokeWidth="2" strokeDasharray="6 4"/>
    <circle cx={x(s.arithmetic_intensity)} cy={y(s.tflops)} r="6" fill="#16877e" stroke="#fff" strokeWidth="2"><title>{fmt(s.arithmetic_intensity)} FLOP/byte · {fmt(s.tflops)} TFLOP/s</title></circle>
    <text x="64" y="18">TFLOP/s · log</text><text x="270" y="188">算术强度 FLOP/byte · log</text>
  </svg><p className="profile-caption">虚线为假设板卡上界，绿点为模拟结果。流量按输入/输出大小估算，非 DRAM 计数器实测。</p></>;
}
function Timeline({ report }) {
  const [iteration, setIteration] = useState('0'), [zoom, setZoom] = useState('1');
  const [selected, setSelected] = useState(null), [filter, setFilter] = useState('all'), [flows, setFlows] = useState(true);
  const viewportRef = useRef(null), traceRef = useRef(null), zoomRef = useRef(1);
  const hovered = useRef(false), pointerX = useRef(null), pendingAnchor = useRef(null);
  const zoomTo = useRef(null);
  zoomTo.current = (value, anchor = null) => {
    const viewport = viewportRef.current, trace = traceRef.current;
    if (!viewport || !trace) return;
    const next = Math.max(1, Math.min(32, Math.round(Number(value) * 100) / 100));
    if (next === zoomRef.current) return;
    const plotLeft = Math.min(190, viewport.clientWidth);
    const chosenX = anchor ?? (hovered.current ? pointerX.current : null)
      ?? plotLeft + (viewport.clientWidth - plotLeft) / 2;
    pendingAnchor.current = { width: trace.getBoundingClientRect().width, scroll: viewport.scrollLeft,
      x: Math.max(plotLeft, Math.min(viewport.clientWidth, chosenX)) };
    zoomRef.current = next;
    setZoom(String(next));
  };
  useLayoutEffect(() => {
    const anchor = pendingAnchor.current;
    if (anchor && viewportRef.current && traceRef.current) {
      viewportRef.current.scrollLeft = anchoredTimelineScroll(anchor.width,
        traceRef.current.getBoundingClientRect().width, anchor.scroll, anchor.x);
      pendingAnchor.current = null;
    }
  }, [zoom]);
  useEffect(() => {
    const viewport = viewportRef.current;
    const isEditing = element => element?.isContentEditable || element?.closest?.('input,select,textarea,[contenteditable="true"],[role="textbox"],[role="combobox"],[role="spinbutton"]');
    const enter = event => { hovered.current = true; move(event); };
    const move = event => { pointerX.current = Math.max(0, Math.min(viewport.clientWidth, event.clientX - viewport.getBoundingClientRect().left)); };
    const leave = () => { hovered.current = false; pointerX.current = null; };
    const reset = () => {
      pendingAnchor.current = null; zoomRef.current = 1; setZoom('1'); viewport.scrollLeft = 0;
    };
    const keydown = event => {
      if (!(hovered.current || viewport.contains(document.activeElement)) || isEditing(document.activeElement) || isEditing(event.target)) return;
      const action = timelineShortcut(event);
      if (!action) return;
      event.preventDefault();
      if (action === 'in' || action === 'out') zoomTo.current(zoomRef.current * (action === 'in' ? 2 : .5));
      else if (action === 'reset') reset();
      else if (action === 'start') viewport.scrollLeft = 0;
      else if (action === 'end') viewport.scrollLeft = viewport.scrollWidth;
      else viewport.scrollLeft += (action === 'left' ? -1 : 1) * viewport.clientWidth * (event.shiftKey ? .65 : .2);
    };
    const wheel = event => {
      const scale = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1;
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault(); move(event);
        zoomTo.current(zoomRef.current * 2 ** (-event.deltaY * scale / 240), pointerX.current);
      } else if (event.shiftKey) {
        event.preventDefault();
        viewport.scrollLeft += (Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY) * scale;
      }
    };
    viewport.addEventListener('pointerenter', enter);
    viewport.addEventListener('pointermove', move);
    viewport.addEventListener('pointerleave', leave);
    viewport.addEventListener('wheel', wheel, { passive: false });
    window.addEventListener('keydown', keydown);
    window.addEventListener('blur', leave);
    return () => {
      viewport.removeEventListener('pointerenter', enter);
      viewport.removeEventListener('pointermove', move);
      viewport.removeEventListener('pointerleave', leave);
      viewport.removeEventListener('wheel', wheel);
      window.removeEventListener('keydown', keydown);
      window.removeEventListener('blur', leave);
    };
  }, []);

  const events = report.capture.events.filter(e => iteration === 'all' || e.iteration === Number(iteration));
  const start = Math.min(...events.map(e => e.start_us)), end = Math.max(...events.map(e => e.start_us + e.duration_us)), duration = end - start;
  const visible = events.filter(e => filter === 'all' || e.category === filter);
  const order = ['CPU / dispatch', 'CPU / wait', 'DMA / H2D', 'SDMA / load', 'Matrix / cluster 0', 'Matrix / cluster 1', 'Vector / core 0', 'Vector / core 1', 'SDMA / store', 'DMA / D2H', 'Sync / fence'];
  const rank = track => order.includes(track) ? order.indexOf(track) : 99;
  const tracks = [...new Set(visible.map(e => e.track))].sort((a, b) => rank(a) - rank(b));
  const lookup = new Map(events.map(e => [e.id, e]));
  const dependencies = selected ? events.flatMap(e => (e.depends_on || []).filter(id => e.id === selected.id || id === selected.id).map(id => [lookup.get(id), e])).filter(([a, b]) => a && tracks.includes(a.track) && tracks.includes(b.track)) : [];
  const linked = new Set(dependencies.flatMap(([a, b]) => [a.id, b.id]));
  const x = e => (e.start_us - start) / duration * 1000;
  return <div className="profile-timeline"><div className="profile-pipeline-banner"><strong>{report.capture.pipeline ? `8 tiles · 双缓冲 · ${new Set(events.map(e => e.track)).size} 条执行轨道` : '历史串行报告'}</strong></div>
    {report.summary.concurrency && <div className="profile-pipeline-stats"><span>峰值并行引擎 <b>{report.summary.concurrency.max_active_engines}</b></span><span>重叠窗口 <b>{fmt(report.summary.concurrency.overlap_pct, 1)}%</b></span><span>kernel 累计工时 <b>{fmt(report.summary.kernel_work_mean_us)} μs / sample</b></span><span>Device 流水线 <b>{fmt(report.summary.mean_us)} μs / sample</b></span></div>}
    <div className="profile-chart-tools"><label>采样范围<select aria-label="时间线采样范围" value={iteration} onChange={e => { setIteration(e.target.value); setSelected(null); }}><option value="all">全部采样</option>{report.capture.samples.map(s => <option key={s.iteration} value={s.iteration}>采样 {s.iteration + 1}</option>)}</select></label><label>缩放<select aria-label="时间线缩放" value={zoom} onChange={e => zoomTo.current(e.target.value)}>{![1, 2, 4, 8, 16, 32].includes(Number(zoom)) && <option value={zoom}>{zoom}×</option>}{[1, 2, 4, 8, 16, 32].map(n => <option key={n} value={n}>{n}×</option>)}</select></label><label>引擎筛选<select aria-label="执行引擎筛选" value={filter} onChange={e => { setFilter(e.target.value); setSelected(null); }}><option value="all">全部执行引擎</option>{Object.entries(categories).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label><label><input type="checkbox" checked={flows} onChange={e => setFlows(e.target.checked)}/>依赖连线</label></div>
    <details className="ui-disclosure profile-shortcuts"><summary>时间线快捷键</summary><p className="profile-navigation-help" id="profile-navigation-help">悬停或聚焦时间线：<kbd>W</kbd>/<kbd>S</kbd> 或 <kbd>+</kbd>/<kbd>−</kbd> 缩放 · <kbd>A</kbd>/<kbd>D</kbd> 或 <kbd>←</kbd>/<kbd>→</kbd> 移动 · <kbd>0</kbd> 复位 · <kbd>Ctrl/⌘</kbd> + 滚轮缩放 · <kbd>Shift</kbd> + 滚轮横移</p></details>
    <div ref={viewportRef} className="profile-trace-scroll" tabIndex={0} role="region" aria-label="可缩放的执行时间线" aria-describedby="profile-navigation-help"><div ref={traceRef} className="profile-trace" style={{ width: `${Number(zoom) * 100}%` }}><div className="profile-axis"><span>ENGINE / TRACK</span><div>{[0, .25, .5, .75, 1].map(n => <span key={n} style={{ left: `${n * 100}%` }}>{fmt(duration * n, 0)} μs</span>)}</div></div>
      <div className="profile-pipeline-body">{tracks.map(track => { const lane = visible.filter(e => e.track === track), stats = report.summary.engines?.find(e => e.track === track); return <div className="profile-track" key={track}><strong><span>{track}</span><small>{stats ? `${fmt(stats.window_pct, 1)}% 全采样占窗 · ` : ''}{lane.length} events</small></strong><div>{lane.map(e => <button key={e.id} className={`profile-event ${engineClass(e)} ${selected?.id === e.id ? 'selected' : ''} ${linked.has(e.id) ? 'linked' : ''}`} style={{ left: `${(e.start_us - start) / duration * 100}%`, width: `${Math.max(.16, e.duration_us / duration * 100)}%` }} title={`${e.name} · tile ${e.tile ?? '—'} · ${fmt(e.duration_us)} μs`} aria-label={`${e.name}，tile ${e.tile ?? '无'}，采样${e.iteration + 1}，${fmt(e.duration_us)}微秒`} onClick={() => setSelected(e)}><span>{e.tile != null ? `T${e.tile} ` : ''}{e.name}</span></button>)}</div></div>; })}
      {flows && <svg className="profile-dependency-lines" viewBox={`0 0 1000 ${Math.max(1, tracks.length) * 64}`} preserveAspectRatio="none" aria-hidden="true"><defs><marker id="profile-flow-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5" fill="#365b72"/></marker></defs>{dependencies.map(([a, b]) => { const ax = x(a) + a.duration_us / duration * 1000, bx = x(b), ay = tracks.indexOf(a.track) * 64 + 32, by = tracks.indexOf(b.track) * 64 + 32; return <path key={`${a.id}-${b.id}`} d={`M${ax},${ay} C${ax + 14},${ay} ${bx - 14},${by} ${bx},${by}`} fill="none" stroke="#365b72" strokeWidth="1.4" markerEnd="url(#profile-flow-arrow)"/>; })}</svg>}
      </div></div></div><div className="profile-legend">{[['matrix','Matrix'],['vector','Vector'],['transfer','DMA'],['sdma','SDMA'],['sync','Fence'],['wait','Host wait']].map(([id, name]) => <span key={id}><i className={id}/>{name}</span>)}</div>
    {selected ? <div className="profile-event-detail"><h3>{selected.name} {selected.tile != null && <span> / Tile {selected.tile} / Buffer {selected.buffer_slot}</span>}</h3><dl><dt>采样 / 轨道</dt><dd>{selected.iteration + 1} · {selected.track}</dd><dt>起点 / 耗时</dt><dd>{fmt(selected.start_us - start)} / {fmt(selected.duration_us)} μs</dd><dt>前置依赖</dt><dd>{(selected.depends_on || []).map(id => { const e = lookup.get(id); return <button key={id} className="profile-dependency-link" onClick={() => { if (e) { setSelected(e); setFilter('all'); } }}>{e?.name || id} · T{e?.tile ?? '—'}</button>; })}{!selected.depends_on?.length && '无'}</dd><dt>数据来源</dt><dd>mock_board · 模拟调度，非真实硬件</dd></dl></div> : <p className="profile-caption">点击事件查看耗时与依赖。</p>}
  </div>;
}
export function ProfilingWorkspace({ token, onSettings }) {
  const [catalog, setCatalog] = useState(preview.catalog), [report, setReport] = useState(preview.report);
  const [caseId, setCaseId] = useState('matmul-1024'), [environment, setEnvironment] = useState('mock-baseline');
  const [warmup, setWarmup] = useState('3'), [repeats, setRepeats] = useState('20'), [seed, setSeed] = useState('42');
  const [history, setHistory] = useState([]), [tab, setTab] = useState('overview'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const attempt = useRef(null);
  useEffect(() => {
    if (!token) { setHistory([]); setReport(preview.report); return; }
    const controller = new AbortController();
    Promise.all([request('/profiling/catalog', { token, signal: controller.signal }), request('/profiling/reports', { token, signal: controller.signal })]).then(([c, h]) => { setCatalog(c); setHistory(h); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [token]);
  async function run() {
    setError(''); setBusy(true);
    const body = { case_id: caseId, environment_id: environment, adapter: 'mock', warmup: Number(warmup), repeats: Number(repeats), seed: Number(seed) };
    const signature = JSON.stringify(body);
    if (attempt.current?.signature !== signature) attempt.current = { signature, key: crypto.randomUUID() };
    try {
      const result = await request('/profiling/reports', { token, method: 'POST', body: { ...body, idempotency_key: attempt.current.key } });
      setReport(result); setTab('overview'); attempt.current = null;
      setHistory(await request('/profiling/reports', { token }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function load(id) { try { setError(''); const result = id === 'bundled-preview' ? preview.report : await request(`/profiling/reports/${id}`, { token }); setReport(result); setCaseId(result.request.case_id); setEnvironment(result.request.environment_id); setWarmup(String(result.request.warmup)); setRepeats(String(result.request.repeats)); setSeed(String(result.request.seed)); } catch (e) { setError(e.message); } }
  async function exportTrace() { try { const trace = report.id === 'bundled-preview' ? preview.trace : await request(`/profiling/reports/${report.id}/trace`, { token }); downloadJson(`${report.id}.trace.json`, trace); } catch (e) { setError(e.message); } }
  async function exportHtml() {
    try {
      const result = report.id === 'bundled-preview' ? { html: preview.html } : await request(`/profiling/reports/${report.id}/html`, { token });
      const url = URL.createObjectURL(new Blob([result.html], { type: 'text/html;charset=utf-8' }));
      const link = document.createElement('a'); link.href = url; link.download = `${report.id}.html`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e.message); }
  }
  const s = report.summary, capture = report.capture, total = Object.values(s.category_us).reduce((a, b) => a + b, 0);
  return <section className="profile-workspace" aria-label="Profiling 工作区"><div className="ui-source-note"><span className="source-label">模拟板卡</span><span>未执行实际 case，性能与正确性均未验证。</span></div>
    <details className="profile-config"><summary><IconActivity size={17}/>新建采样</summary><div className="profile-fields"><label>Case 配置<select aria-label="Profiling case" value={caseId} onChange={e => setCaseId(e.target.value)}>{catalog.cases.map(c => <option key={c.id} value={c.id}>{c.name} · {c.dtype}</option>)}</select></label><label>环境组合<select aria-label="Profiling 环境" value={environment} onChange={e => setEnvironment(e.target.value)}>{catalog.environments.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label><label>预热次数<input aria-label="预热次数" type="number" min="0" max="20" value={warmup} onChange={e => setWarmup(e.target.value)}/></label><label>采样次数<input aria-label="采样次数" type="number" min="1" max="100" value={repeats} onChange={e => setRepeats(e.target.value)}/></label><label>随机种子<input aria-label="随机种子" type="number" min="0" max="65535" value={seed} onChange={e => setSeed(e.target.value)}/></label></div><div className="profile-config-footer"><p>{token ? '通过本地 API 生成并持久保存模拟报告；预热不计入统计。' : '当前为内置报告预览。连接本地 API 后，可按所选配置生成新报告。'}</p>{!token ? <button className="button" onClick={onSettings}>连接本地 API</button> : <button className="button primary" disabled={busy || [warmup, repeats, seed].some(v => v.trim() === '')} onClick={run}><IconPlayerPlay size={18}/>{busy ? '生成模拟报告…' : '生成模拟报告'}</button>}</div></details>
    {error && <p role="alert" className="field-error">{error}</p>}
    <div className="profile-report-heading"><div><h2>{capture.case.name}<span>{capture.case.dtype.toUpperCase()}</span></h2><p className="profile-case-path" title={capture.case.nodeid}>{capture.environment.revision} · {s.sample_count} 次采样</p></div><div className="toolbar-actions"><button className="button" onClick={exportHtml}><IconDownload size={17}/>HTML 报告</button><button className="button" onClick={() => downloadJson(`${report.id}.json`, report)}><IconDownload size={17}/>原始报告</button><button className="button" onClick={exportTrace}><IconDownload size={17}/>Chrome Trace</button></div></div>

    <label className="profile-history">报告记录<select aria-label="Profiling 报告记录" value={report.id} onChange={e => load(e.target.value)}><option value="bundled-preview">内置示例 · baseline · matmul-1024</option>{history.map(r => <option key={r.id} value={r.id}>{new Date(r.created_at * 1000).toLocaleString('zh-CN')} · {r.request.case_id} · {r.request.environment_id} · {r.id.slice(-6)}</option>)}</select></label>
    <div className="profile-metrics"><Metric title="平均 Device 耗时" value={fmt(s.mean_us)} unit="μs" note={s.timing_basis === 'device_pipeline_span' ? '设备流水线窗口，含搬运与同步' : '历史口径：kernel 累计耗时'}/><Metric title="P95 Device 耗时" value={fmt(s.p95_us)} unit="μs" note={`P50 ${fmt(s.p50_us)} μs · nearest-rank P95`}/><Metric title="有效算力" value={fmt(s.tflops)} unit="TFLOP/s" note="假设 FLOPs ÷ Device 窗口"/><Metric title="有效带宽" value={fmt(s.effective_bandwidth_gbs)} unit="GB/s" note="估算流量 ÷ Device 窗口，非实测"/></div>
    <div className="tabs profile-tabs" role="tablist">{[['overview', '性能总览'], ['timeline', '执行时间线'], ['metadata', '环境与原始数据']].map(([id, title]) => <button role="tab" key={id} aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{title}</button>)}</div>
    {tab === 'overview' && <div role="tabpanel"><div className="profile-chart-grid"><article className="profile-chart"><div className="profile-section-title"><h3>重复采样稳定性</h3><span>{s.sample_count} samples</span></div><Samples samples={capture.samples}/><p className="profile-caption">最小 {fmt(s.min_us)} / 最大 {fmt(s.max_us)} μs。相同配置与 seed 可复现相同模拟数据。</p></article><article className="profile-chart"><div className="profile-section-title"><h3>Roofline · 假设模型</h3><span>{s.bound_hint === 'memory' ? '带宽侧上界' : '算力侧上界'}</span></div><Roofline report={report}/></article></div><div className="profile-bottom-grid"><article className="profile-chart"><h3>Kernel 耗时排行</h3><div className="table-scroll"><table className="profile-kernels"><thead><tr><th>Kernel</th><th>调用</th><th>平均 μs</th><th>Kernel 工时占比</th></tr></thead><tbody>{s.kernels.map(k => <tr key={k.name}><td className="mono">{k.name}</td><td>{k.calls}</td><td>{fmt(k.mean_us)}</td><td><div className="profile-share"><i style={{ width: `${k.share_pct}%` }}/></div>{fmt(k.share_pct, 1)}%</td></tr>)}</tbody></table></div></article><article className="profile-chart"><h3>累计事件时长构成</h3><div className="profile-composition">{Object.entries(s.category_us).map(([k, v]) => <span key={k} className={k} style={{ width: `${v / total * 100}%` }} title={`${categories[k]} ${fmt(v / total * 100)}%`}/>)}</div><div className="profile-category-list">{Object.entries(s.category_us).map(([k, v]) => <p key={k}><span>{categories[k]}</span><strong>{fmt(v / total * 100, 1)}%</strong></p>)}</div><p className="profile-caption">事件可以重叠，相加不等于墙钟时间；含Host等待。端到端均值 {fmt(s.wall_mean_us)} μs；Occupancy {capture.counters.occupancy_pct}% 为模拟计数器。</p></article></div></div>}
    {tab === 'timeline' && <div role="tabpanel"><Timeline key={report.id} report={report}/></div>}
    {tab === 'metadata' && <div role="tabpanel" className="profile-raw"><h3>环境快照与数据口径</h3><p>版本均为 mock 标记，未切换真实 SDK；计数器和峰值属于假设，不用于设备验收。</p><pre>{JSON.stringify({ report_id: report.id, source: report.source, correctness: report.correctness, environment: capture.environment, device: capture.device, counters: capture.counters, pipeline: capture.pipeline, timing_basis: s.timing_basis, request: report.request, notes: report.notes }, null, 2)}</pre></div>}

  </section>;
}
