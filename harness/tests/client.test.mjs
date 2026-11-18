import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import React from 'react';
import TestRenderer,{act} from 'react-test-renderer';
const require=createRequire(import.meta.url);
function setup(){
  let entry;
  vm.runInNewContext(readFileSync(new URL('../lib/client.js',import.meta.url),'utf8'),{
    window:{__ModuleLoader__:{load:row=>{entry=row.factory(require);}},addEventListener(){},removeEventListener(){}},console,URLSearchParams,
  });
  const registrations=new Map(),opened=[],tabs=[];
  entry.apply({sidebarRight:{openTab:(kind,options)=>opened.push({kind,options})},
    sidebarRightTabs:{register:definition=>{tabs.push(definition);return()=>{};}},effect:fn=>fn(),
    slots:{inject:(_key,fn)=>fn(),register:(definition,Component)=>{
      registrations.set(definition.key,{definition,Component});return()=>{};
    }}});
  return {registrations,opened,tabs};
}
for(const historical of [false,true])test(historical?'history does not steal focus; manual reopen works':'new tool result opens the workbench with exact selection',async()=>{
  const {registrations,opened}=setup();
  const {definition,Component}=registrations.get('triton_open_page');
  const props={callId:'result',toolName:'triton_open_page',phase:'result',...definition.inject(),
    block:{content:[{type:'text',text:JSON.stringify({status:'ok',triton_view:{
      page:'profiling',selection:{report_id:'report-123'},issued_at:historical?1:Date.now()+1,
    }})}]}};
  let renderer;
  await act(async()=>{renderer=TestRenderer.create(React.createElement(Component,props));});
  assert.equal(opened.length,historical?0:1);
  if(historical)await act(async()=>renderer.root.findByType('button').props.onClick());
  assert.equal(opened[0].kind,'triton-profiling');
  assert.equal(opened[0].options.params.selection.report_id,'report-123');
  await act(async()=>renderer.unmount());
});

test('modules have distinct host entries and embed only their business content',async()=>{
  const {registrations,tabs}=setup();
  const profiling=tabs.find(tab=>tab.kind==='triton-profiling');
  assert.equal(profiling.title(),'Profiling');
  assert(tabs.some(tab=>tab.kind==='triton-tools-cga'));
  assert.equal(tabs.find(tab=>tab.kind==='triton-settings').guide,undefined);
  const {definition,Component}=registrations.get(profiling.id);
  const windowBefore=globalThis.window;
  globalThis.window={addEventListener(){},removeEventListener(){}};
  let renderer;
  try {
    await act(async()=>{renderer=TestRenderer.create(React.createElement(Component,{
      sessionId:'session-1',...definition.inject(),useTabInfo:()=>({tab:{id:'tab-1',navigation:{params:{selection:{report_id:'r1'}}}}}),
    }));});
    const src=renderer.root.findByType('iframe').props.src;
    assert(src.includes('embedded=1'));assert(src.endsWith('#profiling'));
    await act(async()=>renderer.unmount());
  }finally{globalThis.window=windowBefore;}
});
