import { useEffect, useRef, useState } from 'react';
import { IconUser, IconLogout, IconKey, IconPlus, IconSearch } from '@tabler/icons-react';
import { request } from './api';
import './platform.css';

const states = { queued:'排队中', running:'运行中', completed:'已完成', passed:'通过', failed:'失败', error:'执行错误', cancelled:'已取消', interrupted:'已中断', timeout:'超时', skipped:'跳过', no_regression:'未发现回归', candidate:'候选', incomplete:'未完成', component_supported:'组件关联已验证', group_supported:'组件组关联已验证', baseline_invalid:'基线未通过', unstable:'结果波动', boundary_found:'已找到版本范围', budget_exhausted:'预算已用尽', unavailable:'不可用', xfailed:'预期失败', xpassed:'意外通过' };
const types = { daily:'Daily', regression:'回归调查', pytest:'测试运行', profiling:'Profiling' };
const shortId = value => value ? `${value.split('_')[0]} · ${value.slice(-8)}` : '—';
const bytes = value => value < 1024 ? `${value} B` : value < 1048576 ? `${(value/1024).toFixed(1)} KB` : `${(value/1048576).toFixed(1)} MB`;

export function NameLogin({ onLogin, onPreview, busy, error }) {
  const [name,setName]=useState('');
  return <div className="name-login-backdrop"><form className="name-login" aria-label="姓名登录" onSubmit={e=>{e.preventDefault();onLogin(name);}}>
    <IconUser size={26}/><h2>进入工作区</h2><p>输入姓名，继续你的任务与报告。</p>
    <label>姓名<input aria-label="登录姓名" autoComplete="username" autoFocus value={name} maxLength={64} onChange={e=>setName(e.target.value)} placeholder="你的登录名" required/></label>
    <small>同名进入同一空间，不验证真实身份。</small>
    {error&&<p role="alert" className="field-error">{error}</p>}
    <button className="button primary" disabled={busy||!name.trim()}>{busy?'正在进入…':'进入个人空间'}</button>
    <button type="button" className="text-button" onClick={onPreview}>先看浏览器演示</button>
  </form></div>;
}

export function PersonalModels({ user, onLogin }) {
  const [rows,setRows]=useState([]), [editing,setEditing]=useState(null), [name,setName]=useState('');
  const [provider,setProvider]=useState('mock'), [base,setBase]=useState(''), [model,setModel]=useState('mock-planner-v1');
  const [apiKey,setApiKey]=useState(''), [enabled,setEnabled]=useState(true), [isDefault,setDefault]=useState(true);
  const [error,setError]=useState(''), [notice,setNotice]=useState(''), [busy,setBusy]=useState(false), [open,setOpen]=useState(false);
  async function refresh(){setRows(await request('/me/ai-profiles'));}
  useEffect(()=>{if(!user)return;let alive=true;request('/me/ai-profiles').then(r=>{if(alive)setRows(r)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false};},[user?.workspace_id]);
  function edit(r){setEditing(r.id);setName(r.name);setProvider(r.config.provider);setBase(r.config.base_url);setModel(r.config.model);setEnabled(r.enabled);setDefault(r.is_default);setApiKey('');setOpen(true);setNotice('');}
  function create(){setEditing(null);setName('');setProvider('mock');setModel('mock-planner-v1');setApiKey('');setBase('');setEnabled(true);setDefault(true);setOpen(true);setNotice('');setError('');}
  async function save(e){
    e.preventDefault();setBusy(true);setError('');setNotice('');
    try{await request('/me/ai-profiles'+(editing?'/'+editing:''),{method:editing?'PATCH':'POST',body:{name,provider,base_url:base,model,enabled,is_default:isDefault,...(apiKey?{api_key:apiKey}:{})}});setApiKey('');setOpen(false);await refresh();setNotice('配置已保存。');}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function test(r){setBusy(true);setError('');setNotice('');try{const value=await request(`/me/ai-profiles/${r.id}/test`,{method:'POST',body:{}});setNotice(value.message)}catch(e){setError(e.message)}finally{setBusy(false)}}
  if(!user)return <div className="empty-state"><h3>登录后管理模型配置</h3><button className="button primary" onClick={onLogin}>姓名登录</button></div>;
  return <section className="platform-models">
    <div className="ui-section-toolbar"><span className="ui-meta">{rows.length} 个配置</span><button className="button primary" onClick={create}><IconPlus size={16}/>新增配置</button></div>
    <p className="platform-note">Key 加密保存；当前仅支持 Mock 调用，远端 API 可保存配置。</p>
    {error&&<div className="error-banner" role="alert">{error}</div>}{notice&&<p className="ui-feedback" role="status">{notice}</p>}
    {open&&<form className="platform-profile-form" onSubmit={save}>
      <h2 className="ui-form-title">{editing?'编辑配置':'新增配置'}</h2>
      <label>名称<input aria-label="AI配置名称" value={name} onChange={e=>setName(e.target.value)} required maxLength={100}/></label>
      <label>Provider<select aria-label="AI Provider" value={provider} onChange={e=>{setProvider(e.target.value);setModel(e.target.value==='mock'?'mock-planner-v1':'')}}><option value="mock">Mock · 本地验证</option><option value="openai_compatible">OpenAI compatible · 仅保存</option></select></label>
      <label>模型<input aria-label="AI模型ID" value={model} onChange={e=>setModel(e.target.value)} required/></label>
      {provider!=='mock'&&<label>Base URL<input aria-label="AI Base URL" value={base} onChange={e=>setBase(e.target.value)} placeholder="管理员已登记的端点" required/></label>}
      <label>API Key<input aria-label="AI API Key" type="password" autoComplete="new-password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder={editing?'留空保留原密钥':'保存后不可读回'}/></label>
      <div className="platform-profile-flags"><label><input type="checkbox" checked={isDefault} onChange={e=>setDefault(e.target.checked)}/>默认配置</label><label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/>启用</label></div>
      <div className="ui-form-actions"><button type="button" className="button" disabled={busy} onClick={()=>{setOpen(false);setApiKey('')}}>取消</button><button className="button primary" disabled={busy}>{busy?'保存中…':'保存配置'}</button></div>
    </form>}
    {rows.length>0&&<div className="platform-table-scroll"><table className="data-table"><thead><tr><th>名称</th><th>模型 / Provider</th><th>Key</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}>
      <td>{r.name}{r.is_default&&<span className="subtle-badge">默认</span>}</td><td>{r.config.model}<small>{r.config.provider==='mock'?'Mock':r.config.provider}</small></td>
      <td><IconKey size={14}/> {r.has_key?'已保存':'未设置'}</td><td><span className={'platform-result '+(r.enabled?'passed':'')}>{r.enabled?'启用':'停用'}</span></td>
      <td><button className="text-button" onClick={()=>edit(r)}>编辑</button><button className="text-button" disabled={busy||!r.enabled} onClick={()=>test(r)}>{r.config.provider==='mock'?'验证':'测试连接'}</button><details className="ui-inline-details"><summary>版本</summary><code>{r.current_revision}</code></details></td>
    </tr>)}</tbody></table></div>}
    {!rows.length&&!open&&<div className="ui-empty"><h3>尚无模型配置</h3><p>新增一个 Mock 配置，即可用于回归调查。</p></div>}
  </section>;
}

export function DataWorkspace({ user, onLogin }) {
  const [tab,setTab]=useState('tasks'), [kind,setKind]=useState(''), [state,setState]=useState(''), [nodeid,setNodeid]=useState('');
  const [rows,setRows]=useState([]), [cursor,setCursor]=useState(null), [next,setNext]=useState(null), [error,setError]=useState(''), [busy,setBusy]=useState(false);
  const loadSequence=useRef(0);
  async function load(append=false){
    const sequence=++loadSequence.current;setBusy(true);setError('');
    try{
      let path;
      if(tab==='tasks')path='/data/tasks?'+new URLSearchParams({limit:'25',...(kind?{kind}:{}),...(state?{state}:{}),...(append&&next?{cursor:next}:{})});
      else if(tab==='cases')path='/case-results?'+new URLSearchParams({limit:'50',...(nodeid?{nodeid}:{}),...(state?{outcome:state}:{})});
      else path=tab==='sdk'?'/sdk-builds':'/daily-batches';
      const result=await request(path);if(sequence!==loadSequence.current)return;
      setRows(old=>append?[...old,...(result.items||result)]:result.items||result);setCursor(append?next:null);setNext(result.next_cursor||null);
    }catch(e){if(sequence===loadSequence.current)setError(e.message)}finally{if(sequence===loadSequence.current)setBusy(false)}
  }
  useEffect(()=>{setRows([]);setNext(null);setError('');if(user)load();return()=>{loadSequence.current++};},[user?.workspace_id,tab]);
  if(!user)return <div className="empty-state"><h3>登录后查询数据</h3><button className="button primary" onClick={onLogin}>姓名登录</button></div>;
  return <section className="platform-data">
    <div className="tabs pytest-tabs" role="tablist" aria-label="数据分类">{[['tasks','我的任务'],['cases','配置结果'],['sdk','公共 SDK'],['daily','Daily 批次']].map(([id,name])=><button role="tab" aria-selected={tab===id} className={tab===id?'active':''} onClick={()=>{setTab(id);setState('');setKind('')}} key={id}>{name}</button>)}</div>
    {(tab==='sdk'||tab==='daily')&&<p className="platform-note">公共元数据；候选 SDK 尚未安装或通过门禁。</p>}
    <form className="platform-data-filter" onSubmit={e=>{e.preventDefault();load()}}>
      {tab==='tasks'&&<select aria-label="任务类型" value={kind} onChange={e=>setKind(e.target.value)}><option value="">全部类型</option>{Object.entries(types).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select>}
      {(tab==='tasks'||tab==='cases')&&<select aria-label="数据状态筛选" value={state} onChange={e=>setState(e.target.value)}><option value="">全部结果</option>{(tab==='cases'?['passed','failed','skipped','incomplete']:['queued','running','completed','passed','failed','cancelled','error','timeout','interrupted']).map(key=><option key={key} value={key}>{states[key]}</option>)}</select>}
      {tab==='cases'&&<input aria-label="case Node ID" value={nodeid} onChange={e=>setNodeid(e.target.value)} placeholder="精确 Node ID"/>}
      <button className="button" disabled={busy}><IconSearch size={16}/>{busy?'查询中…':'查询'}</button>
    </form>
    {error&&<div className="error-banner" role="alert">{error}</div>}
    <div className="platform-table-scroll"><table className="data-table"><thead><tr><th>{tab==='cases'?'配置':'对象'}</th><th>类型 / 时间</th><th>结果</th><th>关联信息</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}>
      <td className="mono" title={r.id}>{r.nodeid||r.build_id||shortId(r.id)}</td><td>{types[r.kind]||r.business_date||r.build_date||'case'}{r.created_at&&<small>{new Date(r.created_at*1000).toLocaleString('zh-CN')}</small>}</td>
      <td><span className={'platform-result '+(r.outcome||r.state||'')}>{states[r.outcome||r.state]||r.outcome||r.state}</span>{r.duration!=null&&<small>{(r.duration*1000).toFixed(1)} ms</small>}</td>
      <td title={r.task_id||r.id}>{r.job_id||r.source||r.failure_phase||(r.task_id?shortId(r.task_id):'—')}</td>
    </tr>)}</tbody></table></div>
    {!rows.length&&!busy&&<div className="ui-empty"><p>没有匹配记录</p></div>}
    <div className="ui-table-footer"><small className="ui-meta">{rows.length} 条{cursor?' · 已加载更多':''}</small>{next&&<button className="button" disabled={busy} onClick={()=>load(true)}>加载更多</button>}</div>
  </section>;
}

export function AccountSettings({ user, onLogin, onLogout }) {
  const [usage,setUsage]=useState(null);
  useEffect(()=>{let alive=true;if(user)request('/me/usage').then(r=>{if(alive)setUsage(r)}).catch(()=>{});return()=>{alive=false}},[user?.workspace_id]);
  return <section className="platform-account"><h2>个人工作区</h2>{user?<>
    <div className="ui-account-row"><div><strong>{user.name}</strong><p className="platform-note">姓名登录，同名共享一个空间。</p></div><button className="button" onClick={onLogout}><IconLogout size={16}/>切换用户</button></div>
    <dl className="ui-account-usage">{usage&&[['任务',usage.tasks],['本地模型验证',usage.profile_tests],['证据索引',bytes(usage.indexed_storage_bytes)]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    <details className="ui-disclosure"><summary>空间信息</summary><p className="mono">{user.workspace_id}</p><p>姓名不验证真实身份。当前模式适用于可信内网协作。</p></details>
  </>:<button className="button primary" onClick={onLogin}>姓名登录</button>}</section>;
}
