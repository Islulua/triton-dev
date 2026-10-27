import test from 'node:test';
import assert from 'node:assert/strict';
import { request, setSessionContext } from '../src/api.js';

test('session writes use CSRF and same-origin cookies without the legacy bearer sentinel', async () => {
 const original=globalThis.fetch;
 try {
  setSessionContext({workspace_id:'A',csrf_token:'csrf-A'});
  globalThis.fetch=async (url,options)=>{
   assert.equal(url,'/api/task');assert.equal(options.credentials,'same-origin');
   assert.equal(options.headers['X-CSRF-Token'],'csrf-A');
   assert.equal(options.headers.Authorization,undefined);
   return {ok:true,json:async()=>({status:'ok',data:{saved:true}})};
  };
  assert.deepEqual(await request('/task',{method:'POST',token:'session',body:{}}),{saved:true});
 } finally {globalThis.fetch=original;setSessionContext(null)}
});
test('a delayed JSON response from a previous user cannot reach the new user view', async () => {
 const original=globalThis.fetch;
 let finish, decoding;
 const began=new Promise(r=>decoding=r);
 try {
  setSessionContext({workspace_id:'A',csrf_token:'A'});
  globalThis.fetch=async()=>({ok:true,json:()=>{decoding();return new Promise(r=>finish=r)}});
  const pending=request('/data/tasks');await began;
  setSessionContext({workspace_id:'B',csrf_token:'B'});
  finish({status:'ok',data:['private A']});
  await assert.rejects(pending,{name:'AbortError'});
 } finally {globalThis.fetch=original;setSessionContext(null)}
});
