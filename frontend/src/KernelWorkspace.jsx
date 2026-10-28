import { useEffect, useRef, useState } from 'react';
import { IconPlus, IconPlayerPlay, IconRefresh, IconUpload, IconDownload, IconExternalLink, IconX, IconLock, IconLockOpen, IconCode, IconArrowsDiff, IconLink, IconLinkOff, IconPlayerStop } from '@tabler/icons-react';
import { request, downloadJson } from './api';
import { IRCodePanel } from './IRCodePanel';
import { IR_DEMO } from './ir-demo';
import { normalizeIRDocument, linkedLines, acceptCompileResult, parseTraceText, sameSource, needsCompilation } from './ir-model';
import './kernel.css';

const uid = () => crypto.randomUUID();
const tag = doc => doc.source_kind === 'illustrative' ? '示意样例' : doc.source_kind === 'compiled' ? '实际编译' : '导入记录';
const stamp = doc => doc.ui_label || `${doc.kernel} · ${doc.metadata?.hash?.slice(0, 8) || tag(doc)}`;
const withId = (doc, label) => ({ ...normalizeIRDocument(doc), ui_id: typeof doc.id === 'string' ? doc.id : uid(), ui_label: label });
const initialSpec = JSON.stringify({ signature: { X: '*fp32', Y: '*fp32', Z: '*fp32' }, constexprs: { N: 1024, BLOCK: 256 }, target: { backend: 'txda', arch: 'tx82', warp_size: 32 }, options: {} }, null, 2);
const terminal = state => !['queued', 'running'].includes(state);
const STATES = { queued: '等待编译', running: '正在编译', passed: '编译完成', failed: '编译失败', cancelled: '已取消', interrupted: '已中断', error: '执行错误', timeout: '编译超时' };
function Action({ icon: Icon, children, primary, ...props }) { return <button className={`button ${primary ? 'primary' : ''}`} {...props}>{Icon && <Icon size={16}/>} {children}</button>; }

export function KernelWorkspace({ connected, token, user }) {
  const seed = useRef(null); if (!seed.current) seed.current = withId(IR_DEMO, 'vector_add · 示例');
  const [documents, setDocuments] = useState([seed.current]), [activeId, setActiveId] = useState(seed.current.ui_id);
  const active = documents.find(d => d.ui_id === activeId) || documents[0];
  const [code, setCode] = useState(active.source.code), [entry, setEntry] = useState('vector_add'), [spec, setSpec] = useState(initialSpec);
  const [panels, setPanels] = useState([{ id: 'one', stage: 'ttir', docId: null, linked: true }, { id: 'two', stage: 'coreir', docId: null, linked: true }]);
  const [selection, setSelection] = useState({ file: active.source.file_path, line: 11, source: active.source });
  const [baseline, setBaseline] = useState({ code: active.source.code, spec: initialSpec, entry: 'vector_add', compiler: '' });
  const [compilers, setCompilers] = useState([]), [compiler, setCompiler] = useState(''), [auto, setAuto] = useState(false);
  const [task, setTask] = useState(null), [error, setError] = useState(''), [notice, setNotice] = useState(''), [configOpen, setConfigOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false), [layout, setLayout] = useState('columns');
  const input = useRef(null), revision = useRef(0), requestNo = useRef(0), live = useRef(true), channel = useRef(null), channelName = useRef(uid()), snapshot = useRef(null), autoTimer = useRef(null), pollTimer = useRef(null);
  const taskRef = useRef(task); taskRef.current = task;
  const dirty = code !== active.source.code, compiling = task && !terminal(task.state);
  const compileDirty = needsCompilation({ code, spec, entry, compiler }, baseline) || active.source_kind !== 'compiled';
  const patchPanel = (id, patch) => setPanels(items => items.map(p => p.id === id ? { ...p, ...patch } : p));
  function selectDocument(doc) { revision.current++; requestNo.current++; clearTimeout(autoTimer.current); clearTimeout(pollTimer.current); setAuto(false); setActiveId(doc.ui_id); setCode(doc.source.code); setEntry(doc.kernel); setSelection(null); setError(''); setTask(null);
    if (doc.metadata?.signature) { const restored = JSON.stringify({ signature: doc.metadata.signature, constexprs: doc.metadata.constexprs || {}, target: doc.metadata.target || JSON.parse(initialSpec).target, options: doc.metadata.options || {} }, null, 2); setSpec(restored); setBaseline({ code: doc.source.code, spec: restored, entry: doc.kernel, compiler: doc.metadata.compiler_id || compiler }); if (doc.metadata.compiler_id) setCompiler(doc.metadata.compiler_id); }
  }
  useEffect(() => {
    live.current = true;
    const bus = new BroadcastChannel(`triton-ir-${channelName.current}`); channel.current = bus;
    bus.onmessage = ({ data }) => {
      if (data?.type === 'ready') bus.postMessage({ type: 'snapshot', value: snapshot.current });
      if (data?.type === 'select' && !snapshot.current?.dirty && typeof data.docId === 'string' && Number.isInteger(data.line)) {
        const doc = snapshot.current?.documents.find(d => d.ui_id === data.docId);
        const loc = doc?.stages.find(s => s.id === data.stage)?.mapping?.[data.line];
        if (loc) setSelection({ ...loc, source: doc.source });
      }
    };
    return () => { live.current = false; requestNo.current++; clearTimeout(autoTimer.current); clearTimeout(pollTimer.current); bus.postMessage({ type: 'closed' }); bus.close(); };
  }, []);
  useEffect(() => {
    snapshot.current = { documents, panels, selection, activeId, dirty };
    channel.current?.postMessage({ type: 'snapshot', value: snapshot.current });
  }, [documents, panels, selection, activeId, dirty]);
  useEffect(() => {
    if (!connected) { setCompilers([]); setCompiler(''); return; }
    const abort = new AbortController();
    request('/ir/compilers', { token, signal: abort.signal }).then(data => { setCompilers(data.compilers); setCompiler(data.compilers[0]?.id || ''); }).catch(e => { if (e.name !== 'AbortError') setNotice('当前服务尚未配置 IR 编译器；可继续导入文件查看。'); });
    return () => abort.abort();
  }, [connected, token, user?.workspace_id]);
  useEffect(() => {
    clearTimeout(autoTimer.current);
    if (auto && compileDirty && connected && compiler) autoTimer.current = setTimeout(() => compile(), 800);
    return () => clearTimeout(autoTimer.current);
  }, [code, spec, entry, compiler, auto, active.ui_id]);
  useEffect(() => {
    if (!connected || !historyOpen) return;
    const abort = new AbortController();
    request('/ir/compilations', { token, signal: abort.signal }).then(async result => {
      const records = await Promise.all(result.items.filter(r => r.state === 'passed').slice(0, 15).map(r => request(`/ir/compilations/${r.id}`, { token, signal: abort.signal })));
      if (abort.signal.aborted) return;
      const history = records.filter(r => r.document).map(r => withId({ ...r.document, id: r.id }, `${r.document.kernel} · r${r.spec.revision}`));
      setDocuments(items => [...items, ...history.filter(d => !items.some(old => old.ui_id === d.ui_id))]);
    }).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => abort.abort();
  }, [connected, historyOpen, token]);
  function edit(value) { revision.current++; setCode(value); setSelection(null); setError(''); }
  async function compile() {
    clearTimeout(autoTimer.current); clearTimeout(pollTimer.current);
    const identity = { revision: revision.current, request: ++requestNo.current };
    let parsed;
    try { parsed = JSON.parse(spec); } catch { setError('编译配置不是有效的 JSON。'); return; }
    if (!connected || !compiler) { setConfigOpen(true); setNotice('需要连接已登记隔离编译器的服务；示意样例不会模拟编译。'); return; }
    setError(''); setNotice('');
    try {
      if (taskRef.current && !terminal(taskRef.current.state)) await request(`/ir/compilations/${taskRef.current.id}/cancel`, { token, method: 'POST', body: {} });
      if (!live.current || identity.request !== requestNo.current) return;
      const record = await request('/ir/compilations', { token, method: 'POST', body: { spec: { ...parsed, code, entry, compiler_id: compiler, revision: identity.revision }, idempotency_key: uid() } });
      if (!live.current || identity.request !== requestNo.current) return;
      setTask(record);
      const poll = async record => {
        if (!live.current || identity.request !== requestNo.current) return;
        setTask(record);
        if (terminal(record.state)) {
          if (record.document) {
            const doc = withId({ ...record.document, id: record.id }, `${record.document.kernel} · r${identity.revision}`);
            setDocuments(items => [doc, ...items]);
            if (acceptCompileResult({ revision: revision.current, request: requestNo.current }, identity)) { setActiveId(doc.ui_id); setBaseline({ code, spec, entry, compiler }); setSelection(null); }
            else setNotice('编译已完成，源码已有更新；结果保存在历史中。');
          }
          if (record.error) setError(record.error.message);
          return;
        }
        pollTimer.current = setTimeout(async () => { try { await poll(await request(`/ir/compilations/${record.id}`, { token })); } catch (e) { if (live.current && identity.request === requestNo.current) setError(e.message); } }, 500);
      };
      await poll(record);
    } catch (e) { if (live.current && identity.request === requestNo.current) setError(e.message); }
  }
  async function cancel() { if (!task) return; const currentRequest = requestNo.current, taskId = task.id; try { const result = await request(`/ir/compilations/${taskId}/cancel`, { token, method: 'POST', body: {} }); if (live.current && currentRequest === requestNo.current && taskRef.current?.id === taskId) setTask(result); } catch (e) { if (live.current && currentRequest === requestNo.current) setError(e.message); } }
  async function importFile(event) {
    const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
    setError('');
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error('文件超过 2 MiB 导入上限。');
      let docs;
      if (connected) {
        const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        docs = (await request('/ir/import', { token, method: 'POST', body: { data: btoa(binary) } })).documents;
      } else {
        let bytes = await file.arrayBuffer();
        if (/\.gz$/i.test(file.name)) {
          const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader(), chunks = []; let size = 0;
          try { while (true) { const part = await reader.read(); if (part.done) break; size += part.value.length; if (size > 8 * 1024 * 1024) throw new Error('解压后文件超过 8 MiB。'); chunks.push(part.value); } } finally { await reader.cancel(); }
          bytes = await new Blob(chunks).arrayBuffer();
        }
        docs = parseTraceText(new TextDecoder().decode(bytes));
      }
      const imported = docs.map(d => withId(d));
      setDocuments(items => [...imported, ...items]); selectDocument(imported[0]);
      setNotice(`已导入 ${imported.length} 个编译实例；${connected ? '由 TritonParse 解析器处理位置映射。' : '离线读取已有映射，原始 IR 的位置解析需连接服务。'}`);
    } catch (e) { setError(`导入失败：${e.message}`); }
  }
  function popout(panel) {
    const url = new URL(window.location.href); url.search = ''; url.searchParams.set('ir_window', channelName.current); url.searchParams.set('ir_panel', panel.id); url.hash = 'kernel';
    return url.href;
  }
  const showLines = (doc, panel) => !dirty && panel.linked && sameSource(selection?.source, doc.source) ? linkedLines(doc, panel.stage, selection) : [];
  return <div className="kernel-workspace">
    <div className="ir-page-title"><div><span className="ir-eyebrow">KERNEL DEBUGGING & TUNING</span><h1>Kernel Lab</h1><p>编辑 Kernel、追踪 IR，为调试与调优提供依据。</p></div><div className="ir-title-actions"><input ref={input} type="file" accept=".json,.ndjson,.gz" hidden onChange={importFile}/><Action icon={IconUpload} onClick={() => input.current.click()}>导入 Trace</Action><Action icon={IconDownload} onClick={() => downloadJson(`${active.kernel}-ir.json`, active)}>导出</Action></div></div>
    <div className="ir-context-strip"><span className={`ir-origin ${active.source_kind}`}>{tag(active)}</span><strong>{active.kernel}</strong><span className="ir-context-divider"/><span>{active.stages.length} 个 IR 阶段</span><span>{active.metadata?.backend || active.metadata?.target?.backend || '导入环境'}</span><button onClick={() => setHistoryOpen(!historyOpen)} className="ir-history-toggle">编译历史 <span>{documents.length}</span></button></div>
    {active.source_kind === 'illustrative' && <p className="ir-provenance">当前为手写交互样例，未执行 Triton 编译。点击源码第 11 行查看多阶段联动；导入真实 Trace 或连接编译器后使用实际结果。</p>}
    {notice && <div className="ir-notice" role="status">{notice}<button aria-label="关闭提示" onClick={() => setNotice('')}><IconX size={14}/></button></div>}
    {error && <div className="error-banner" role="alert">{error}</div>}
    {historyOpen && <div className="ir-history">{documents.map(doc => <button className={activeId === doc.ui_id ? 'active' : ''} key={doc.ui_id} onClick={() => selectDocument(doc)}><IconCode size={15}/><span>{stamp(doc)}</span><small>{tag(doc)}</small></button>)}</div>}
    <div className="ir-controls"><div className="ir-controls-left"><button className={`ir-config-toggle ${configOpen ? 'selected' : ''}`} onClick={() => setConfigOpen(!configOpen)} aria-expanded={configOpen}>编译配置 <span>{compiler ? compilers.find(c => c.id === compiler)?.label : '未配置编译器'}</span></button><label className="ir-auto"><input type="checkbox" checked={auto} disabled={!connected || !compiler} onChange={e => setAuto(e.target.checked)}/>自动编译 <small>800ms</small></label></div><div className="ir-controls-right">{dirty && <span className="ir-dirty">源码已修改 · IR 待更新</span>}{task && <span className="ir-task-state" role="status">{STATES[task.state] || task.state}</span>}{compiling ? <Action icon={IconPlayerStop} onClick={cancel}>取消</Action> : <Action primary icon={IconPlayerPlay} onClick={compile}>编译 Kernel</Action>}</div></div>
    {configOpen && <div className="ir-configuration"><div><label>编译环境<select value={compiler} onChange={e => { revision.current++; setCompiler(e.target.value); }}>{!compilers.length && <option value="">未登记隔离编译器</option>}{compilers.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label><label>Kernel 入口<input value={entry} onChange={e => { revision.current++; setEntry(e.target.value); }}/></label><p>源码在服务器登记的隔离执行器中编译。只请求编译，不启动 kernel。</p></div><label>参数类型 / constexpr / target / options<textarea aria-label="编译配置 JSON" spellCheck="false" value={spec} onChange={e => { revision.current++; setSpec(e.target.value); }}/></label></div>}
    <div className="ir-workbench-toolbar"><span><IconLink size={15}/>{selection ? `源码 L${selection.line} · 已关联 ${active.stages.filter(s => linkedLines(active, s.id, selection).length).length} 个阶段` : dirty ? '旧映射已停用，编译后恢复联动' : '点击任一代码行，查看对应源码与 IR'}</span><div><select aria-label="面板布局" value={layout} onChange={e => setLayout(e.target.value)}><option value="columns">并排布局</option><option value="grid">网格布局</option></select><Action icon={IconPlus} disabled={panels.length >= 6} onClick={() => setPanels(items => [...items, { id: uid(), stage: active.stages[items.length % active.stages.length].id, linked: true, docId: null }])}>添加 IR 窗口</Action></div></div>
    <div className={`ir-workbench ${layout}`}>
      <section className="ir-source-panel"><div className="ir-panel-heading"><span><IconCode size={16}/><strong>{active.source.file_path.split('/').pop()}</strong></span><span className="ir-language">TRITON PYTHON</span></div><div className="ir-source-info"><span>可编辑</span><button onClick={() => { edit(active.source.code); setSelection(null); }} disabled={!dirty}><IconRefresh size={13}/>还原</button></div><div className="ir-editor"><IRCodePanel path={`source-${active.ui_id}.py`} content={code} language="python" readOnly={false} onChange={edit} startLine={active.source.start_line} highlights={!dirty && sameSource(selection?.source, active.source) ? [selection.line - active.source.start_line + 1] : []} onLine={line => { if (!dirty) setSelection({ file: active.source.file_path, line: line + active.source.start_line - 1, source: active.source }); }}/></div><div className="ir-panel-footer"><span>{code.split('\n').length} 行</span><span>{dirty ? '未编译的修改' : tag(active)}</span></div></section>
      {panels.map(panel => {
        const doc = documents.find(d => d.ui_id === panel.docId) || active;
        const stage = doc.stages.find(s => s.id === panel.stage) || doc.stages[0];
        const effective = { ...panel, stage: stage.id };
        const lines = showLines(doc, effective);
        const comparison = documents.find(d => d.ui_id === panel.compareId)?.stages.find(s => s.id === stage.id);
        return <section className="ir-output-panel" key={panel.id}><div className="ir-panel-heading"><select aria-label={`IR 阶段 ${panel.id}`} value={stage.id} onChange={e => patchPanel(panel.id, { stage: e.target.value })}>{doc.stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select><div className="ir-panel-actions"><button title={panel.linked ? '关闭联动' : '开启联动'} aria-label={panel.linked ? '关闭联动' : '开启联动'} onClick={() => patchPanel(panel.id, { linked: !panel.linked })}>{panel.linked ? <IconLink size={15}/> : <IconLinkOff size={15}/>}</button><a title="弹出独立窗口" aria-label="弹出独立窗口" href={popout(effective)} target="_blank" rel="noopener noreferrer"><IconExternalLink size={15}/></a><button title="关闭 IR 窗口" aria-label="关闭 IR 窗口" onClick={() => setPanels(items => items.filter(p => p.id !== panel.id))}><IconX size={15}/></button></div></div><div className="ir-source-info"><button title={panel.docId ? '跟随当前版本' : '固定当前版本'} onClick={() => patchPanel(panel.id, { docId: panel.docId ? null : doc.ui_id })}>{panel.docId ? <IconLock size={13}/> : <IconLockOpen size={13}/>}</button><select aria-label={`IR 编译记录 ${panel.id}`} value={panel.docId || ''} onChange={e => patchPanel(panel.id, { docId: e.target.value || null })}><option value="">跟随当前版本</option>{documents.map(d => <option key={d.ui_id} value={d.ui_id}>{stamp(d)}</option>)}</select><span className="ir-match-count">{lines.length ? `${lines.length} 行关联` : stage.mapping_status === 'unavailable' ? '无位置映射' : '—'}</span></div><div className="ir-editor"><IRCodePanel path={`${doc.ui_id}-${panel.id}-${stage.id}`} content={stage.content} highlights={lines} original={comparison?.content} onLine={line => { if (!dirty && panel.linked && stage.mapping[line]) setSelection({ ...stage.mapping[line], source: doc.source }); }}/></div><div className="ir-panel-footer"><span>{stage.content.split('\n').length} 行</span><label title="比较相同阶段的其他编译记录"><IconArrowsDiff size={13}/><select aria-label={`IR 差异对比 ${panel.id}`} value={panel.compareId || ''} onChange={e => patchPanel(panel.id, { compareId: e.target.value || null })}><option value="">选择版本对比</option>{documents.filter(d => d.ui_id !== doc.ui_id && d.stages.some(s => s.id === stage.id)).map(d => <option key={d.ui_id} value={d.ui_id}>{stamp(d)}</option>)}</select></label></div></section>;
      })}
    </div>
    {task?.diagnostics && <details className="ir-diagnostics"><summary>编译诊断与日志</summary><pre>{task.diagnostics}</pre></details>}
  </div>;
}

export function IRDetachedWorkspace() {
  const params = new URLSearchParams(window.location.search), [snapshot, setSnapshot] = useState(null), [closed, setClosed] = useState(false), bus = useRef(null);
  const [stageId, setStageId] = useState('');
  useEffect(() => {
    const channel = new BroadcastChannel(`triton-ir-${params.get('ir_window')}`); bus.current = channel;
    channel.onmessage = ({ data }) => { if (data?.type === 'snapshot') setSnapshot(data.value); if (data?.type === 'closed') { setSnapshot(null); setClosed(true); } };
    channel.postMessage({ type: 'ready' }); return () => channel.close();
  }, []);
  const panel = snapshot?.panels.find(p => p.id === params.get('ir_panel'));
  const doc = snapshot?.documents.find(d => d.ui_id === (panel?.docId || snapshot.activeId));
  const stage = doc?.stages.find(s => s.id === (stageId || panel?.stage)) || doc?.stages[0];
  if (!doc || !stage) return <div className="ir-detached-empty">{closed ? '原工作台已关闭或切换用户，源内容已清除。' : '正在连接原工作台…'}</div>;
  return <div className="ir-detached"><div className="ir-panel-heading"><strong>{doc.kernel} <small> / {tag(doc)}</small></strong><select aria-label="独立窗口 IR 阶段" value={stage.id} onChange={e => setStageId(e.target.value)}>{doc.stages.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}</select></div><IRCodePanel content={stage.content} path={`detached-${doc.ui_id}-${stage.id}`} highlights={!snapshot.dirty && sameSource(snapshot.selection?.source, doc.source) ? linkedLines(doc, stage.id, snapshot.selection) : []} onLine={line => bus.current.postMessage({ type: 'select', docId: doc.ui_id, stage: stage.id, line })}/></div>;
}
