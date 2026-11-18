import React, { useEffect, useRef } from 'react';
import { PAGES, MODULES, moduleFor } from './protocol.js';
export const inject=['slots','sidebarRight','sidebarRightTabs'];
const ID='triton-dev-harness';

function Workbench(props) {
  const {tab}=props.useTabInfo();
  const frame=useRef(null);
  const params=tab.navigation.params||{};
  const page=PAGES.includes(params.page)?params.page:(props.defaultPage||'home');
  const query=new URLSearchParams({embedded:'1',harness_session:props.sessionId,selection:JSON.stringify(params.selection||{})});
  useEffect(()=>{
    const navigate=event=>{
      if(event.origin!==window.location.origin || event.source!==frame.current?.contentWindow)return;
      if(event.data?.type!=='triton:navigate' || !PAGES.includes(event.data.page))return;
      props.openPage(event.data.page);
    };
    window.addEventListener('message',navigate);
    return()=>window.removeEventListener('message',navigate);
  },[props.openPage]);
  return <iframe ref={frame} key={tab.id+page+query} title="triton-dev 工作台" src={'/triton/?'+query+'#'+page}
    style={{width:'100%',height:'100%',minHeight:0,border:0,background:'#f5f8f8'}} />;
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
  const openPage=(page,selection={})=>{
    const module=moduleFor(page);
    if(module)ctx.sidebarRight.openTab(module.kind,{params:{page,selection}});
  };
  const registerBody=(id,defaultPage='home')=>ctx.effect(()=>ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({
    name:'sidebar.right.pane.tab',key:id,inject:()=>({openPage,defaultPage}),
  },Workbench)));
  for(const module of MODULES){
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:module.id,kind:module.kind,priority:'extension',title:()=>module.title,
      ...(module.showInGuide?{guide:[{id:module.page,order:35+MODULES.indexOf(module),title:()=>module.title,
        description:()=> 'Triton · '+module.title}]}:{})}));
    registerBody(module.id,module.page);
  }
  // Old retained tabs remain readable, but no longer contribute a second application menu.
  ctx.effect(()=>ctx.sidebarRightTabs.register({id:ID,kind:'triton',priority:'extension',title:()=> 'Triton'}));
  registerBody(ID);
  // Tool registry is generated during build; only our names receive our result view.
  for(const name of TOOL_NAMES) {
    ctx.effect(()=>ctx.slots.inject('tool.call.toolview',()=>ctx.slots.register({name:'tool.call.toolview',key:name,
      inject:()=>({reveal:(callId,view,manual)=>{
        if(!PAGES.includes(view.page))return;
        if(!manual&&(seen.has(callId)||view.issued_at<started))return;
        seen.add(callId);
        openPage(view.page,view.selection);
      }})},ToolResult)));
  }
}
