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
    window:{__ModuleLoader__:{load:row=>{entry=row.factory(require);}}},console,
  });
  const registrations=new Map(),opened=[];
  entry.apply({sidebarRight:{openTab:(kind,options)=>opened.push({kind,options})},
    sidebarRightTabs:{register:()=>()=>{}},effect:fn=>fn(),
    slots:{inject:(_key,fn)=>fn(),register:(definition,Component)=>{
      registrations.set(definition.key,{definition,Component});return()=>{};
    }}});
  return {registrations,opened};
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
  assert.equal(opened[0].kind,'triton');
  assert.equal(opened[0].options.params.selection.report_id,'report-123');
  await act(async()=>renderer.unmount());
});
