import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { routePath } from './protocol.js';

export function worker(config, request, signal) {
  return new Promise((resolve, reject) => {
    const args = ['-m','triton_dev.harness','--sdk-root',config.sdkRoot,'--cache-root',config.cacheRoot];
    if (!request) args.push('--catalog');
    const child = spawn(config.python, args, {cwd:config.repository, stdio:['pipe','pipe','pipe'], signal});
    let out='', err='';
    child.stdout.on('data', b => {out+=b; if(out.length>8*1024*1024) child.kill();});
    child.stderr.on('data', b => {err=(err+b).slice(-4096);});
    child.on('error', reject);
    child.on('close', code => {
      try {resolve(JSON.parse(out));} catch {reject(new Error('Triton worker failed ('+code+'): '+err));}
    });
    child.stdin.end(request ? JSON.stringify(request) : '');
  });
}

export class Backend {
  constructor(config) {
    this.config=config;
    this.origin=new URL(config.backend);
    if (!['127.0.0.1','localhost','[::1]'].includes(this.origin.hostname) || this.origin.protocol!=='http:') throw new Error('Demo backend must use loopback HTTP');
    this.sessions=new Map();
  }
  async session(id, signal) {
    if (!id || typeof id!=='string' || id.length>256) throw new Error('Harness session required');
    if (!this.sessions.has(id)) {
      const pending=(async()=>{
        const name='harness-'+createHash('sha256').update(id).digest('hex').slice(0,24);
        const r=await fetch(new URL('/api/sessions',this.origin), {method:'POST', signal,
          headers:{'Content-Type':'application/json',Origin:this.origin.origin},body:JSON.stringify({name})});
        const json=await r.json();
        if(!r.ok || json.status!=='ok') throw new Error(json.error?.message || 'Backend login failed');
        const cookie=r.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');
        return {cookie,csrf:json.data.csrf_token};
      })();
      this.sessions.set(id,pending);
      pending.catch(()=>this.sessions.delete(id));
    }
    return this.sessions.get(id);
  }
  async fetch(id,path,{method='GET',body,signal}={}) {
    if(!path.startsWith('/api/') || path.startsWith('//') || path.includes('..')) throw new Error('Invalid backend path');
    const session=await this.session(id,signal);
    return fetch(new URL(path,this.origin),{method,signal,redirect:'error',headers:{
      Cookie:session.cookie,Origin:this.origin.origin,'X-CSRF-Token':session.csrf,
      ...(body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:JSON.stringify(body)});
  }
  async call(id,route,args,signal) {
    const r=await this.fetch(id,routePath(route,args.params,args.query),{method:route.method,body:route.method==='GET'?undefined:(args.body||{}),signal});
    const type=r.headers.get('content-type')||'';
    if(type.includes('json')) return r.json();
    const text=await r.text();
    if(text.length>1024*1024) throw new Error('Artifact too large for model context; use its download page');
    return {status:r.ok?'ok':'failed',data:{content_type:type,text},error:r.ok?null:{message:'HTTP '+r.status}};
  }
}
