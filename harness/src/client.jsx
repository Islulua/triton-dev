import React, { useEffect } from 'react';
import { PAGES } from './protocol.js';
export const inject=['slots','sidebarRight','sidebarRightTabs'];
const ID='triton-dev-harness';

function Workbench(props) {
  const {tab}=props.useTabInfo();
  const params=tab.navigation.params||{};
  const page=PAGES.includes(params.page)?params.page:'home';
  const query=new URLSearchParams({harness_session:props.sessionId,selection:JSON.stringify(params.selection||{})});
  return <iframe key={tab.id+page+query} title="triton-dev 工作台" src={'/triton/?'+query+'#'+page}
    style={{width:'100%',height:'100%',minHeight:600,border:0,background:'#f5f8f8'}} />;
}
function ToolResult(props) {
  let value;
  if(props.phase==='result') {
    try {value=JSON.parse(props.block.content.filter(b=>b.type==='text').map(b=>b.text).join(''));} catch {}
  }
  const view=value?.triton_view;
  useEffect(()=>{if(view)props.reveal(props.callId,view,false);},[view?.issued_at,props.callId]);
  return <div style={{padding:12,border:'1px solid #d6e5e1',borderRadius:8}}>
    <strong>{props.toolName}</strong> · {props.phase==='result'?(value?.status||'completed'):'执行中'}
    {view&&<button onClick={()=>props.reveal(props.callId,view,true)} style={{marginLeft:12}}>在工作台查看</button>}
    {value&&<details><summary>结果与证据</summary><pre style={{maxHeight:280,overflow:'auto',whiteSpace:'pre-wrap'}}>{JSON.stringify(value,null,2)}</pre></details>}
  </div>;
}
export function apply(ctx) {
  const started=Date.now(),seen=new Set();
  ctx.effect(()=>ctx.sidebarRightTabs.register({id:ID,kind:'triton',priority:'extension',title:()=> 'triton-dev',
    guide:[{id:'workbench',order:35,title:()=> 'triton-dev 工作台',description:()=> '测试、环境、Profiling、Kernel Lab 与布局工具'}]}));
  ctx.effect(()=>ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:ID},Workbench)));
  // Tool registry is generated during build; only our names receive our result view.
  for(const name of TOOL_NAMES) {
    ctx.effect(()=>ctx.slots.inject('tool.call.toolview',()=>ctx.slots.register({name:'tool.call.toolview',key:name,
      inject:()=>({reveal:(callId,view,manual)=>{
        if(!PAGES.includes(view.page))return;
        if(!manual&&(seen.has(callId)||view.issued_at<started))return;
        seen.add(callId);
        ctx.sidebarRight.openTab('triton',{params:{page:view.page,selection:view.selection}});
      }})},ToolResult)));
  }
}
