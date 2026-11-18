import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { apply } from '../src/index.js';
import { Backend } from '../src/backend.js';
import { routeName, routePath, navigation } from '../src/protocol.js';
const repository=new URL('../../',import.meta.url).pathname;
const config={repository,python:repository+'.venv/bin/python',sdkRoot:'/tmp/triton-harness-tests/sdks',cacheRoot:'/tmp/triton-harness-tests/cache'};

test('every tool registers without replacing built-ins; layouts use real workbench logic',async()=>{
 const definitions=new Map([['existing_plugin_tool',{name:'existing_plugin_tool'}]]),effects=[];
 let route;
 await apply({tools:{register:d=>{assert(!definitions.has(d.name),d.name);definitions.set(d.name,d);}},
  webServer:{register:r=>{route=r;return()=>{route=undefined;};}},effect:fn=>effects.push(fn())},config);
 assert(definitions.size>100);assert(definitions.has('existing_plugin_tool'));assert.equal(route.path,'/triton');assert.equal(route.auth,'required');
 const cga=await definitions.get('triton_layout_cga').execute({source:'[[0, 1], [1, 0]]'});
 assert.equal(cga.triton_view.page,'tools-cga');assert(cga.data.groups.length>0);
 const blocked=await definitions.get('triton_layout_blocked').execute({shape:'8, 32',source:JSON.stringify({sizePerThread:[1,2],threadsPerWarp:[2,16],warpsPerCTA:[2,1],order:[1,0]})});
 assert.equal(blocked.triton_view.page,'tools-blocked');assert(blocked.data);
 const result=await definitions.get('triton_cli_capabilities').execute({}, {signal:new AbortController().signal});
 assert.equal(result.status,'ok');
 const denied=await definitions.get('triton_cli_env_exec').execute({command:['echo','bad']},{signal:new AbortController().signal});
 assert.equal(denied.error.code,'REGISTERED_JOB_REQUIRED');
 for(const dispose of effects)if(typeof dispose==='function')dispose();
 assert.equal(route,undefined);
});

test('session cookies and CSRF are retained on host and isolated by Harness session',async()=>{
 let logins=0;const calls=[];
 const server=createServer(async(req,res)=>{
  let text='';for await(const b of req)text+=b;
  calls.push({url:req.url,cookie:req.headers.cookie,csrf:req.headers['x-csrf-token']});
  res.setHeader('Content-Type','application/json');
  if(req.url==='/api/sessions'){logins++;res.setHeader('Set-Cookie','td_session=s'+logins+'; HttpOnly');res.end(JSON.stringify({status:'ok',data:{csrf_token:'c'+logins}}));}
  else res.end(JSON.stringify({status:'ok',data:{id:'report-1'}}));
 });server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const b=new Backend({backend:'http://127.0.0.1:'+server.address().port});
  const route={method:'POST',path:'/api/profiling/reports'};
  await b.call('one',route,{body:{adapter:'mock'}});await b.call('one',route,{});await b.call('two',route,{});
  assert.equal(logins,2);assert.equal(calls[1].cookie,'td_session=s1');assert.equal(calls[1].csrf,'c1');assert.equal(calls.at(-1).cookie,'td_session=s2');
 }finally{server.closeAllConnections();server.close();}
});

test('navigation and route parameters cannot select arbitrary endpoints',()=>{
 assert.throws(()=>navigation('https://evil.invalid'));assert.throws(()=>routePath({path:'/api/tasks/{task_id}'},{task_id:'../sessions'}));
 assert.equal(routeName({method:'GET',path:'/api/tasks/{task_id}'}),'triton_api_get_tasks_task_id');
 assert.equal(routePath({path:'/api/tasks/{task_id}'},{task_id:'abc'}),'/api/tasks/abc');
});
