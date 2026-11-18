// Run against an explicitly started local demo backend; never calls a model or device.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {apply} from '../src/index.js';
const repository=new URL('../../',import.meta.url).pathname;
const tools=new Map();
await apply({tools:{register:t=>tools.set(t.name,t)},webServer:{register:()=>()=>{}},effect:fn=>fn()},
 {repository,python:repository+'.venv/bin/python',backend:process.env.TRITON_TEST_BACKEND||'http://127.0.0.1:8766'});
const exec={agent:{sessionId:'smoke-'+randomUUID()},signal:new AbortController().signal};
async function call(name,args={}){const v=await tools.get(name).execute(args,exec);assert.equal(v.status,'ok',JSON.stringify(v.error));return v;}
async function wait(id){for(let n=0;n<120;n++){const v=await call('triton_api_get_tasks_task_id',{params:{task_id:id}});if(!['queued','running'].includes(v.data.state))return v.data;await new Promise(r=>setTimeout(r,250));}throw new Error('Task timed out');}
const jobs=(await call('triton_api_get_jobs')).data;
const job=jobs.find(j=>j.kind==='pytest');assert(job,'Register a CPU demo pytest job first');
const collection=await call('triton_api_post_tasks',{body:{job_id:job.job_id,idempotency_key:randomUUID()}});
const collected=await wait(collection.data.id);assert.equal(collected.state,'passed');
const nodeids=collected.collection.map(c=>c.nodeid);assert(nodeids.length>0);
const selected=nodeids.filter(n=>n.includes('test_parameter[64]'));assert.equal(selected.length,1);
const run=await call('triton_api_post_pytest_runs',{body:{collection_id:collected.id,nodeids:selected,isolation:'case',idempotency_key:randomUUID()}});
const result=await wait(run.data.id);assert.equal(result.state,'passed');assert.equal(run.triton_view.selection.task_id,run.data.id);
const catalog=(await call('triton_api_get_profiling_catalog')).data;
console.log('Profiling catalog keys:',Object.keys(catalog));
const cases=catalog.cases,environments=catalog.environments;
const report=await call('triton_api_post_profiling_reports',{body:{case_id:cases[0].id,environment_id:environments[0].id,adapter:'mock',warmup:1,repeats:3,seed:42,idempotency_key:randomUUID()}});
assert.equal(report.triton_view.page,'profiling');
await call('triton_api_get_profiling_reports_report_id',{params:{report_id:report.data.id}});
console.log('PASS: Harness tools → real CPU collection/run → persistent result → mock Profiling → report navigation');
