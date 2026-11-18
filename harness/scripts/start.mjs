/** Start the two owned processes; retained dependencies are installed separately. */
import {spawn} from 'node:child_process';
import {mkdir,writeFile,access} from 'node:fs/promises';
import {resolve,join} from 'node:path';
const repository=resolve(new URL('../../',import.meta.url).pathname);
const root=process.env.TRITON_HARNESS_ROOT||'/workspace/triton-harness';
const python=join(repository,'.venv/bin/python');
const dsh=process.env.TRITON_DSH_BIN||join(root,'runtime/node_modules/.bin/dsh');
const port=Number(process.env.TRITON_BACKEND_PORT||8766);
await Promise.all([access(python),access(dsh),access(join(repository,'harness/lib/client.js')),access(join(repository,'frontend/dist/client/index.html'))]);
await mkdir(join(root,'backend'),{recursive:true});await mkdir(join(root,'documents'),{recursive:true});
const children=[];let stopping=false;
function stop(){if(stopping)return;stopping=true;for(const c of children)c.kill('SIGTERM');}
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,stop);
function launch(command,args,env={}){const c=spawn(command,args,{cwd:repository,stdio:'inherit',env:{...process.env,...env}});children.push(c);c.on('error',e=>{console.error(e.message);stop();process.exitCode=1;});c.on('exit',code=>{if(!stopping){process.exitCode=code||0;stop();}});return c;}
try {
 await access(join(root,'demo/jobs.json'));
} catch {
 const p=spawn(python,['examples/pytest_server_demo.py','--workdir',join(root,'demo')],{cwd:repository,stdio:'inherit'});
 await new Promise((ok,bad)=>{p.on('exit',c=>c===0?ok():bad(new Error('Demo registry preparation failed')));p.on('error',bad);});
}
// Refuse accidental attachment to an unrelated service.
try{const r=await fetch(`http://127.0.0.1:${port}/api/capabilities`,{signal:AbortSignal.timeout(500)});if(r)throw new Error('Backend port already occupied; choose TRITON_BACKEND_PORT');}catch(e){if(e.message.includes('occupied'))throw e;}
const backend=launch(join(repository,'.venv/bin/triton-dev'),['serve','--multi-user','--jobs',join(root,'demo/jobs.json'),'--cache-root',join(root,'backend'),'--port',String(port)],{TRITON_DEV_DATABASE_URL:process.env.TRITON_DEV_DATABASE_URL||'sqlite:///'+join(root,'backend/platform.sqlite')});
let ready=false;
for(let n=0;n<100&&!stopping;n++){
 try {const r=await fetch(`http://127.0.0.1:${port}/api/capabilities`);if(r.ok){ready=true;break;}} catch {}
 await new Promise(r=>setTimeout(r,100));
}
if(!ready){stop();throw new Error('Backend did not become ready');}
const patch=join(root,'triton.patch.yml');
await writeFile(patch,JSON.stringify([{insert:[{id:'triton-dev-workbench',name:'triton-dev-harness',config:{repository,python,backend:`http://127.0.0.1:${port}`,sdkRoot:join(root,'sdks'),cacheRoot:join(root,'cache'),uiRoot:join(repository,'frontend/dist/client')}}]},{id:'workspace-controller',config:{documentsDirectory:join(root,'documents')}}],null,2));
launch(dsh,['web','--patch',patch,'--no-open','--port',process.env.TRITON_HARNESS_PORT||'3080'],{DSH_HOME:process.env.DSH_HOME||join(root,'home')});
