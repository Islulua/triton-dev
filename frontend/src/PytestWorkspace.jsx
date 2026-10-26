import { useEffect, useRef, useState } from 'react';
import { request, downloadJson } from './api';
import './pytest.css';
import { groupCases, selectConfigurations } from './pytest-model';
import { RunOverview } from './RunOverview';
import { TestReportPreview } from './TestReportPreview';
import { buildRunStatistics, filterStatisticRows, RESULT_NAMES } from './run-statistics';
const names = {passed:'通过',failed:'失败',skipped:'跳过',xfailed:'预期失败',xpassed:'意外通过',pending:'未开始',running:'运行中',incomplete:'未完成',queued:'排队中',cancelled:'已取消',error:'执行错误',timeout:'超时',interrupted:'已中断',finished:'已退出',crashed:'崩溃',not_started:'未启动'};
const active = r => ['queued','running'].includes(r?.state);
const time = n => n ? new Date(n*1000).toLocaleString('zh-CN') : '—';
function Badge({value}) { return <span className={`pytest-status ${value}`}>{names[value]||value}</span>; }
function GroupCheckbox({ selected, total, ...props }) {
  const ref=useRef(null);
  useEffect(()=>{ if(ref.current)ref.current.indeterminate=selected>0&&selected<total; },[selected,total]);
  return <input ref={ref} type="checkbox" checked={total>0&&selected===total} {...props}/>;
}
function GroupRows({group,full,selected,count,chosen,failed,latest,expanded,onExpand,onGroup,onToggle}) {
  return <><tr className="pytest-group-row"><td><GroupCheckbox aria-label={`选择用例 ${group.id}`} selected={count} total={group.cases.length} onChange={e=>onGroup(e.target.checked)}/></td><td><button className="pytest-group-toggle" aria-expanded={expanded} aria-label={`展开配置 ${group.id}`} onClick={onExpand}><span aria-hidden="true">{expanded?'▾':'▸'}</span><span className="mono">{group.id}</span></button><span className="secondary-line">{full.cases.length} 个配置 · 已选 {chosen}{group.cases.length!==full.cases.length?` · 筛选显示 ${group.cases.length} 项`:''}</span></td><td>{group.markers.join(', ')||'—'}</td><td>{failed?<Badge value="failed"/>:<span className="muted">{full.cases.some(c=>latest.has(c.nodeid))?'见配置结果':'未运行'}</span>}{failed>0&&<span className="secondary-line">{failed} 个配置失败</span>}</td></tr>
  {expanded&&<tr className="pytest-configuration-row"><td colSpan="4"><div className="pytest-configuration-list">{group.cases.map(c=><div key={c.nodeid} className={selected.includes(c.nodeid)?'chosen':''}><input type="checkbox" aria-label={`选择配置 ${c.nodeid}`} checked={selected.includes(c.nodeid)} onChange={()=>onToggle(c.nodeid)}/><details><summary><strong>{c.parameter_id||'默认配置'}</strong><span>{Object.entries(c.parameters||{}).map(([key,value])=>`${key}=${value}`).join(', ')||c.nodeid}</span></summary><dl className="key-values"><dt>Node ID</dt><dd className="mono">{c.nodeid}</dd><dt>逻辑 ID</dt><dd>{c.case_id||'未标注'}</dd><dt>位置</dt><dd>{c.nodeid.split('::')[0]}:{c.line}</dd><dt>Fixtures</dt><dd>{c.fixtures.join(', ')}</dd></dl></details>{latest.has(c.nodeid)?<Badge value={latest.get(c.nodeid)}/>:<span className="muted tiny">未运行</span>}</div>)}</div></td></tr>}</>;
}
function WorkerLogs({reports=[]}) {
  const [worker,setWorker]=useState('all');
  const valid=worker==='all'||reports.some(w=>w.worker_id===worker)?worker:'all';
  const visible=valid==='all'?reports:reports.filter(w=>w.worker_id===valid);
  return <div className="pytest-workers"><p className="pytest-help">按真实 worker ID 归档。阶段结束后追加捕获输出；triton_dev_log 可主动写入执行进度。控制进程日志另列。</p>
    <div className="worker-cards">{reports.map(w=><button key={w.worker_id} className={valid===w.worker_id?'selected':''} onClick={()=>setWorker(w.worker_id)}><strong>{w.worker_id==='controller'?'controller · 控制进程':w.worker_id}</strong><Badge value={w.state}/><span>{w.summary.total} 个配置 · {w.summary.passed} 通过 / {w.summary.failed} 失败</span><small>PID {w.pids.join(', ')||'尚未启动'}</small></button>)}</div>
    <label className="pytest-worker-select">查看日志<select aria-label="选择 worker 日志" value={valid} onChange={e=>setWorker(e.target.value)}><option value="all">全部 workers</option>{reports.map(w=><option key={w.worker_id}>{w.worker_id}</option>)}</select></label>
    {!reports.length&&<p role="status">尚无 worker 事件。旧记录可能没有 worker 元数据。</p>}
    {visible.map(w=><div key={w.worker_id}><h3>{w.worker_id} · <Badge value={w.state}/></h3>{w.error&&<div className="error-banner">{w.error}</div>}{(w.tail_truncated||w.disk_truncated)&&<p className="pytest-help">{w.tail_truncated?'当前展示日志尾部。':''}{w.disk_truncated?'本 worker 的磁盘日志达到保留上限。':''}</p>}<pre className="log-view expanded">{w.log||'暂无 case 日志；初始化和调度信息请查看进程日志。'}</pre></div>)}
  </div>;
}
export function PytestWorkspace({token,jobs,records}) {
  const projects=jobs.filter(j=>j.kind==='pytest');
  const [project,setProject]=useState(projects[0]?.job_id||'');
  const [collectionId,setCollectionId]=useState('');
  const [selected,setSelected]=useState([]);
  const [isolation,setIsolation]=useState('case');
  const [workers,setWorkers]=useState(1);
  const [extensions,setExtensions]=useState({});
  const [expanded,setExpanded]=useState(new Set());
  const [surface,setSurface]=useState('collection');
  const [runId,setRunId]=useState('');
  const [caseId,setCaseId]=useState('');
  const [query,setQuery]=useState('');
  const [failedOnly,setFailedOnly]=useState(false);
  const [tab,setTab]=useState('overview');
  const [resultFilter,setResultFilter]=useState({});
  const [busy,setBusy]=useState(false);
  const [optimistic,setOptimistic]=useState(null);
  const [error,setError]=useState('');
  const pending=useRef(false),keys=useRef(new Map());
  const displayed=optimistic&&!records.some(r=>r.id===optimistic.id)?[optimistic,...records]:records;
  const matching=displayed.filter(r=>r.job_id===project&&r.request?.kind==='pytest').sort((a,b)=>b.created_at-a.created_at);
  const collections=matching.filter(r=>r.request.operation==='collect');
  const collection=collections.find(r=>r.id===collectionId)||collections[0];
  const history=matching.filter(r=>r.request.operation==='run');
  const run=history.find(r=>r.id===runId);
  const runCollection=collections.find(c=>c.id===run?.request.source_id);
  const parentRun=history.find(r=>r.id===run?.parent);
  const runStats=buildRunStatistics(run||{},runCollection?.collection||[],parentRun);
  const resultVisible=filterStatisticRows(runStats,resultFilter);
  const inspectResults=filter=>{setResultFilter(filter);setCaseId('');setTab('phases');};
  useEffect(()=>{setSelected([]);setQuery('');setFailedOnly(false);setExpanded(new Set());},[collection?.id]);
  const projectInfo=projects.find(p=>p.job_id===project);
  useEffect(()=>{setWorkers(1);setIsolation('case');setExtensions({});},[project]);
  const schemas=projectInfo?.extensions||[];
  const maxWorkers=projectInfo?.max_workers||8;
  const options=Object.fromEntries(schemas.map(d=>[d.name,extensions[d.name]??d.default]));
  const latest=new Map();
  history.filter(r=>r.request.source_id===collection?.id).forEach(r=>(r.test_results||[]).forEach(c=>{if(!latest.has(c.nodeid))latest.set(c.nodeid,c.outcome);}));
  const visible=(collection?.collection||[]).filter(c=>`${c.nodeid} ${c.markers.join(' ')} ${JSON.stringify(c.parameters)}`.toLowerCase().includes(query.toLowerCase())&&(!failedOnly||latest.get(c.nodeid)==='failed'));
  const groups=groupCases(visible);
  const fullGroups=new Map(groupCases(collection?.collection||[]).map(g=>[g.id,g]));
  const current=resultVisible.find(c=>c.nodeid===caseId)||resultVisible.find(c=>c.outcome==='failed')||resultVisible[0];
  async function post(path,body,done){
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    const signature=path+JSON.stringify(body),key=keys.current.get(signature)||crypto.randomUUID();keys.current.set(signature,key);
    try{const result=await request(path,{token,method:'POST',body:{...body,idempotency_key:key}});keys.current.delete(signature);setOptimistic(result);done(result);}
    catch(e){setError(e.message);}finally{pending.current=false;setBusy(false);}
  }
  const collect=()=>post('/tasks',{job_id:project},r=>{setCollectionId(r.id);setSurface('collection');});
  const open=r=>{setRunId(r.id);setSurface('result');setCaseId('');setResultFilter({});setTab('overview');};
  const start=()=>post('/pytest/runs',{collection_id:collection.id,nodeids:selected,isolation,workers:Number(workers),extensions:options},open);
  const rerun=mode=>post(`/tasks/${run.id}/rerun`,{mode},open);
  async function cancel(){try{await request(`/tasks/${run.id}/cancel`,{token,method:'POST',body:{}});}catch(e){setError(e.message);}}
  async function downloadArtifact(item){
    try{const response=await fetch(`/api/tasks/${run.id}/artifacts/${item.id}`,{headers:{Authorization:`Bearer ${token}`}});
      if(!response.ok)throw new Error('附件下载失败或超过 10 MiB 限制');
      const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
      link.href=url;link.download=item.path.split('/').at(-1);link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e.message);}
  }
  const toggle=id=>setSelected(old=>old.includes(id)?old.filter(n=>n!==id):[...old,id]);
  if(!projects.length)return <div className="info">尚未登记 pytest 项目。请在服务的 jobs.json 中登记 kind: pytest、项目目录、解释器和测试入口。普通任务仍可在“命令任务”中运行。</div>;
  return <section className="pytest-workspace" aria-label="真实 pytest 工作区">
    <div className="pytest-project"><label>测试项目<select aria-label="测试项目" value={project} onChange={e=>{setProject(e.target.value);setCollectionId('');setSurface('collection');setError('');}}>{projects.map(p=><option key={p.job_id}>{p.job_id}</option>)}</select></label><span className="subtle-badge">真实 pytest · 已登记项目</span></div>
    {error&&<div className="error-banner" role="alert">{error}</div>}
    <div className="section-toolbar"><div className="tabs" role="tablist">{[['collection','收集与选择'],['history','pytest 运行记录'],...(surface==='result'?[['result','运行详情']]:[])].map(([id,label])=><button key={id} role="tab" aria-selected={surface===id} className={surface===id?'active':''} onClick={()=>setSurface(id)}>{label}</button>)}</div><button className="button" disabled={busy} onClick={collect}>重新收集</button></div>
    {surface==='collection'&&<>
      <p className="pytest-help">先收集源码快照，再选择参数化 nodeid。重新收集生成新快照，不会覆盖旧运行。</p>
      <label className="pytest-collection-label">收集记录<select aria-label="收集记录" value={collection?.id||''} onChange={e=>setCollectionId(e.target.value)}><option disabled value="">尚无收集记录</option>{collections.map(c=><option key={c.id} value={c.id}>{time(c.created_at)} · {names[c.state]} · {c.collection?.length??'—'} 项 · {c.id.slice(-8)}</option>)}</select></label>
      {!collection&&<div className="empty"><h2>收集这个项目的用例</h2><p>收集会执行导入与 conftest，使用独立进程和工作目录。</p><button className="button primary" disabled={busy} onClick={collect}>开始收集</button></div>}
      {collection&&<><div className="pytest-collection-state"><Badge value={collection.state}/><span>{collection.collection?.length??'—'} 个参数实例</span><span className="mono">源码 {collection.source_snapshot?.sha256?.slice(0,12)||'快照准备中'}</span></div>
      {collection.error&&<div className="error-banner">{collection.error.code}：{collection.error.message}</div>}
      {(collection.stages||[]).filter(s=>s.type==='collection_error').map((s,i)=><pre className="log-view" key={i}>{s.longrepr}</pre>)}
      {active(collection)&&<p role="status">收集中，记录会自动刷新…</p>}
      {collection.state==='passed'&&<><div className="pytest-filters"><input aria-label="筛选真实用例" placeholder="搜索 nodeid、marker 或参数…" value={query} onChange={e=>setQuery(e.target.value)}/><label><input type="checkbox" checked={failedOnly} onChange={e=>setFailedOnly(e.target.checked)}/>本快照最近失败</label></div>
        <div className="pytest-run-settings"><label>执行模式<select aria-label="执行模式" value={isolation} onChange={e=>{setIsolation(e.target.value);setWorkers(e.target.value==='xdist'?Math.min(4,maxWorkers):1);}}><option value="case">每个配置独立进程</option><option value="session">整次运行独立进程</option><option value="xdist">xdist 并行</option></select></label><label>Workers<input aria-label="Workers" type="number" min="1" max={maxWorkers} step="1" value={workers} onChange={e=>{setWorkers(e.target.value);if(Number(e.target.value)>1)setIsolation('xdist');}}/></label><span className="muted">项目上限 {maxWorkers}</span></div>
        <p className="pytest-help">{isolation==='xdist'?`使用 xdist 的 ${workers||'—'} 个测试 worker（另有控制进程）。worker 内共享 session 和本次源码目录，HOME/临时目录/缓存按 worker 分开。`:'逐配置模式每个参数实例启动新进程；session 模式在一次运行内共享状态。将 workers 设为大于 1 会切换到 xdist。'}</p>
        <details className="pytest-extensions"><summary>扩展运行配置 · {schemas.length} 项</summary><div className="pytest-extension-fields">{schemas.map(spec=><label key={spec.name}><strong>{spec.title}</strong>{spec.schema.type==='boolean'?<input type="checkbox" aria-label={spec.title} checked={options[spec.name]} onChange={e=>setExtensions(old=>({...old,[spec.name]:e.target.checked}))}/>:spec.schema.enum?<select aria-label={spec.title} value={options[spec.name]} onChange={e=>setExtensions(old=>({...old,[spec.name]:e.target.value}))}>{spec.schema.enum.map(value=><option key={value}>{value}</option>)}</select>:<input aria-label={spec.title} type={spec.schema.type==='integer'?'number':'text'} min={spec.schema.minimum} max={spec.schema.maximum} step="1" value={options[spec.name]} onChange={e=>setExtensions(old=>({...old,[spec.name]:spec.schema.type==='integer'?Number(e.target.value):e.target.value}))}/>}<small>{spec.description}</small></label>)}</div>{!schemas.length&&<p>本项目没有开放扩展选项。</p>}</details>
        <div className="pytest-group-heading">{groups.length} 个逻辑用例 · 当前显示 {visible.length} 个配置</div>
        <div className="table-scroll"><table className="data-table pytest-cases pytest-groups"><thead><tr><th><GroupCheckbox aria-label="选择全部真实用例" selected={visible.filter(c=>selected.includes(c.nodeid)).length} total={visible.length} onChange={e=>setSelected(old=>selectConfigurations(old,visible.map(c=>c.nodeid),e.target.checked))}/></th><th>逻辑用例 / 配置</th><th>Markers</th><th>最近结果</th></tr></thead><tbody>{groups.map(group=>{
          const full=fullGroups.get(group.id)||group,ids=group.cases.map(c=>c.nodeid),count=ids.filter(id=>selected.includes(id)).length;
          const chosen=full.cases.filter(c=>selected.includes(c.nodeid)).length;
          const failed=full.cases.filter(c=>latest.get(c.nodeid)==='failed').length;
          return <GroupRows key={group.id} group={group} full={full} selected={selected} count={count} chosen={chosen} failed={failed} latest={latest} expanded={expanded.has(group.id)} onExpand={()=>setExpanded(old=>{const next=new Set(old);next.has(group.id)?next.delete(group.id):next.add(group.id);return next;})} onGroup={checked=>setSelected(old=>selectConfigurations(old,ids,checked))} onToggle={toggle}/>;
        })}</tbody></table></div>
        {!visible.length&&<p className="pytest-help">没有匹配配置；空收集不会计为测试通过。</p>}
        <div className="pytest-launch"><strong>已选 {selected.length} 个配置</strong><span>{isolation==='xdist'?`xdist × ${workers}`:isolation==='case'?'逐配置独立进程':'单次 session'}</span><button className="button primary" disabled={busy||!selected.length||selected.length>500||!Number.isInteger(Number(workers))||Number(workers)<1||Number(workers)>maxWorkers} onClick={start}>运行所选配置</button></div><p className="pytest-help">复选框按参数化 nodeid 提交。例如展开一个 32 配置的用例，只勾选一项，就只运行该项。每次最多选择 500 个配置。</p></>}
      {collection.state!=='passed'&&(collection.result||collection.live_logs)&&<pre className="log-view">{collection.result?.stdout||collection.live_logs?.stdout}{collection.result?.stderr||collection.live_logs?.stderr}</pre>}</>}
    </>}
    {surface==='history'&&<>{!history.length?<p className="pytest-help">尚无 pytest 执行记录，先收集并运行用例。</p>:<div className="table-scroll"><table className="data-table pytest-history"><thead><tr><th>运行 / 来源</th><th>结果</th><th>用例统计</th><th>隔离 / 时间</th></tr></thead><tbody>{history.map(r=><tr key={r.id}><td><button className="row-name mono" onClick={()=>open(r)}>{r.id.slice(-12)}</button><span className="secondary-line">{r.parent?`复测自 ${r.parent.slice(-12)}`:'首次运行'}</span><span className="secondary-line mono">{r.source_snapshot?.sha256?.slice(0,12)}</span></td><td><Badge value={r.state}/></td><td>{r.summary?.passed||0} 通过 / {r.summary?.failed||0} 失败<span className="secondary-line">共 {r.summary?.total??r.request.nodeids.length} 项</span></td><td>{r.request.isolation==='xdist'?`xdist × ${r.request.workers}`:r.request.isolation==='case'?'逐配置':'session'}<span className="secondary-line">{time(r.created_at)}</span></td></tr>)}</tbody></table></div>}</>}
    {surface==='result'&&(!run?<p role="status">正在读取新运行记录…</p>:<>
      <button className="back-link" onClick={()=>setSurface('history')}>← 返回 pytest 运行记录</button><div className="pytest-run-heading"><div><h2>pytest 运行详情</h2><p className="mono">{run.id}</p></div><div className="toolbar-actions"><Badge value={run.state}/>{active(run)?<button className="button" onClick={cancel}>取消 pytest 运行</button>:<><button className="button primary" disabled={busy||!run.summary?.failed} onClick={()=>rerun('failed')}>仅复测失败项</button><button className="button" disabled={busy} onClick={()=>rerun('all')}>原配置全部复测</button></>}<button className="button" onClick={()=>downloadJson(`${run.id}.json`,run)}>导出 pytest 报告</button></div></div>
      {run.parent&&<div className="info">复测来自 <span className="mono">{run.parent}</span>。原始记录保留，沿用原源码快照和解释器配置。</div>}{run.error&&<div className="error-banner" role="alert">{run.error.code}：{run.error.message}</div>}{run.error?.details&&Object.keys(run.error.details).length>0&&<pre className="json-view">{JSON.stringify(run.error.details,null,2)}</pre>}
      {!['overview','report'].includes(tab)&&<div className="pytest-summary" aria-label="用例统计">{['total','passed','failed','skipped','xfailed','xpassed','incomplete','pending','running'].map(k=><div key={k}><strong>{run.summary?.[k]||0}</strong><span>{k==='total'?'全部':names[k]}</span></div>)}</div>}
      <div className="pytest-tabs tabs" role="tablist">{[['overview','运行总览'],['report','报告预览'],['phases','用例与阶段'],['workers','Worker 日志'],['logs','进程日志'],['snapshot','环境与源码'],['evidence','附件与证据']].map(([id,label])=><button key={id} role="tab" aria-selected={tab===id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</div>
      {tab==='report'&&<TestReportPreview key={run.id} record={run} collection={runCollection?.collection||[]} onInspect={inspectResults}/>}
      {tab==='overview'&&<RunOverview key={run.id} record={run} collection={runCollection?.collection||[]} parent={parentRun} onInspect={inspectResults}/>}
      {tab==='phases'&&Object.keys(resultFilter).length>0&&<div className="runstats-filter"><span>统计筛选 · {[resultFilter.operator,resultFilter.status&&RESULT_NAMES[resultFilter.status],resultFilter.phase&&`${resultFilter.phase} 阶段失败`,resultFilter.nodeid].filter(Boolean).join(' / ')} · 匹配 {resultVisible.length} 个配置</span><button className="text-button" onClick={()=>setResultFilter({})}>清除筛选</button></div>}
      {tab==='phases'&&<div className="pytest-result-layout"><div className="pytest-case-nav" aria-label="执行结果列表">{resultVisible.map(c=><button key={c.nodeid} className={current?.nodeid===c.nodeid?'selected':''} onClick={()=>setCaseId(c.nodeid)}><Badge value={c.outcome}/><span><span className="mono">{c.nodeid}</span><small className="secondary-line">{c.workers?.join(', ')||'等待分配'}</small></span></button>)}</div><div className="pytest-case-detail">{current?<><h3 className="mono">{current.nodeid}</h3><p className="pytest-help">耗时 {current.duration.toFixed(3)} 秒 · {current.failure_phase?`${current.failure_phase} 阶段失败`:names[current.outcome]}</p>{['setup','call','teardown'].map(phase=>{const report=current.stages.find(s=>s.when===phase);return <details key={phase} open={report?.outcome==='failed'} className="pytest-phase"><summary><strong>{phase}</strong><small>{report?.worker_id||'—'}</small><Badge value={report?.outcome||(active(run)?'pending':'incomplete')}/><span>{report?`${report.duration.toFixed(3)}s`:'无报告'}</span></summary>{report&&<><pre className="log-view">{report.longrepr||'该阶段没有失败堆栈。'}</pre>{(report.stdout||report.stderr)&&<><h4>捕获输出（累计）</h4><pre className="log-view">{report.stdout}{report.stderr}</pre></>}<h4>结构化 context / properties</h4><pre className="json-view">{JSON.stringify({context:report.context,properties:report.properties},null,2)}</pre></>}</details>;})}</>:<p>本次筛选没有匹配配置，或尚未收到结果。尚无报告不等于通过。</p>}</div></div>}
      {tab==='workers'&&<WorkerLogs reports={run.worker_reports||[]}/>}
      {tab==='logs'&&<><p className="pytest-help">执行中展示已写入输出；pytest 捕获内容在阶段报告查看。终态保留有界日志尾部。</p><pre className="log-view expanded">{run.result?.stdout||run.live_logs?.stdout||'暂无 stdout'}{'\n'}{run.result?.stderr||run.live_logs?.stderr}</pre>{(run.stages||[]).filter(s=>s.type==='collection_error').map((s,i)=><pre className="log-view" key={i}>{s.longrepr}</pre>)}</>}
      {tab==='snapshot'&&<><p className="pytest-help">源码按 SHA256 留档。登记解释器启动前检查包版本；设备、原生库和网络没有容器化。</p><pre className="json-view">{JSON.stringify({source:run.source_snapshot,isolation:run.isolation,interpreter:run.request.environment?.interpreter||run.request.python,runtime:run.runtime,collection:run.request.source_id,nodeids:run.request.nodeids,workers:run.request.workers||1,extensions:run.request.extensions,extension_versions:run.request.extension_versions},null,2)}</pre></>}
      {tab==='evidence'&&<><p className="pytest-help">context、record_property、阶段捕获输出随报告保存。附件由 case 显式写入 triton_dev_artifact_dir；分享原始报告前检查敏感信息。</p><div className="pytest-artifacts">{(run.artifacts||[]).map(item=><button className="text-button" key={item.id} onClick={()=>downloadArtifact(item)}>{item.path.split('/').slice(-2).join('/')} · {item.size} bytes · 下载</button>)}</div>{!run.artifacts?.length&&<p className="pytest-help">没有已登记附件。</p>}<button className="button" onClick={()=>downloadJson(`${run.id}.json`,run)}>导出完整返回记录</button></>}
    </>)}
    <div className="info pytest-boundary">进程与目录隔离适用于受信任测试。设备、网络、绝对路径和解释器安装目录仍共享；服务任务串行调度；单次任务可配置 xdist 测试 workers。</div>
  </section>;
}
