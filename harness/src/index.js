import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { worker, Backend } from './backend.js';
import { PAGES, navigation, routeName, pageFor } from './protocol.js';

export const name='triton-dev-harness';
export const inject=['tools','webServer'];
const repository=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml','.ttf':'font/ttf'};
const output={schema:{type:'object',additionalProperties:true},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]};

export async function apply(ctx, options={}) {
  const config={repository,python:resolve(repository,'.venv/bin/python'),backend:'http://127.0.0.1:8765',
    sdkRoot:'/workspace/triton-harness/sdks',cacheRoot:'/workspace/triton-harness/cache',
    uiRoot:resolve(repository,'frontend/dist/client'),enableWrites:true,...options};
  const backend=new Backend(config);
  const catalog=await worker(config);
  if(!catalog.commands || !catalog.routes) throw new Error('Invalid Triton capability catalog');
  function register(tool) {
    // Registration effects belong to this plugin scope; no replacement of built-in services.
    ctx.tools.register({...tool,output});
  }
  const wrap=(value,page,selection={})=>({...value,triton_view:navigation(page,selection)});
  for(const command of catalog.commands) {
    register({name:command.name,description:command.description+(command.available?'':' [Requires registered job; direct shell is unavailable]'),
      parameters:command.inputSchema,
      async execute(args,exec) {
        if(!config.enableWrites && command.effects!=='read_only') throw new Error('Triton writes disabled');
        return wrap(await worker(config,{command:command.command,arguments:args},exec.signal),'env');
      }});
  }
  for(const route of catalog.routes) {
    const properties={params:{type:'object',properties:Object.fromEntries([...route.path.matchAll(/\{([^}]+)\}/g)].map(m=>[m[1],{type:'string'}])),additionalProperties:false},
      query:{type:'object',additionalProperties:{type:'string'}}};
    if(route.method!=='GET') properties.body={type:'object',additionalProperties:true,description:'Domain request JSON. Fields used by this handler: '+route.bodyFields.join(', ')};
    register({name:routeName(route),description:route.method+' '+route.path+' — '+route.description,
      parameters:{type:'object',properties,additionalProperties:false},
      async execute(args,exec) {
        if(!config.enableWrites && route.method!=='GET') throw new Error('Triton writes disabled');
        const session=exec.agent?.sessionId;
        if(!session) throw new Error('Triton API requires a Harness agent session');
        const value=await backend.call(session,route,args,exec.signal);
        return wrap(value,pageFor(route.path),{...args.params,...(value.data?.job_id?{job_id:value.data.job_id}:{}),...(value.data?.request?.operation?{operation:value.data.request.operation}:{}),...(value.data?.id?{task_id:value.data.id,report_id:value.data.id,batch_id:value.data.id}:{}),...(value.data?.task_id?{task_id:value.data.task_id}:{})});
      }});
  }
  register({name:'triton_open_page',description:'Open a Triton workbench page in this conversation; selection can carry task_id, report_id, source, shape or layout.',
    parameters:{type:'object',properties:{page:{type:'string',enum:PAGES},selection:{type:'object',additionalProperties:true}},required:['page'],additionalProperties:false},
    async execute(args){return {status:'ok',triton_view:navigation(args.page,args.selection)};}});
  for(const [kind,page] of [['cga','tools-cga'],['blocked','tools-blocked']]) {
    register({name:'triton_layout_'+kind,description:'Compute '+kind+' layout using the exact workbench implementation, then display it. Logical mapping only; no kernel executes.',
      parameters:{type:'object',properties:{source:{type:'string'},shape:{type:'string'}},required:kind==='blocked'?['source','shape']:['source'],additionalProperties:false},
      async execute(args) {
        const module=await import(new URL('../../frontend/src/tools/'+(kind==='cga'?'cga-layout':'blocked-layout')+'.js',import.meta.url));
        const model=kind==='cga'?module.buildCgaLayout(args.source):module.buildBlockedLayout(args.shape,args.source);
        return {status:'ok',data:model,triton_view:navigation(page,args)};
      }});
  }
  // Serve a preserved UI in an authenticated Harness-owned namespace, never claim /api or root.
  ctx.effect(()=>ctx.webServer.register({kind:'prefix',path:'/triton',auth:'required',async handler(req,res){
    try {
      const url=new URL(req.url,'http://harness.local');
      if(url.pathname.startsWith('/triton/api/')) {
        const id=req.headers['x-triton-session'];
        if(!id || Array.isArray(id)) {res.writeHead(400);res.end('Harness session required');return;}
        let body=''; for await(const b of req){body+=b;if(body.length>4*1024*1024)throw new Error('Request too large');}
        const r=await backend.fetch(id,url.pathname.slice('/triton'.length)+url.search,{method:req.method,body:body?JSON.parse(body):undefined});
        res.writeHead(r.status,{'Content-Type':r.headers.get('content-type')||'application/octet-stream','Cache-Control':'no-store'});
        res.end(Buffer.from(await r.arrayBuffer())); return;
      }
      if(url.pathname==='/triton'){res.writeHead(302,{Location:'/triton/'});res.end();return;}
      const relative=decodeURIComponent(url.pathname.slice('/triton/'.length))||'index.html';
      const file=resolve(config.uiRoot,relative);
      if(!file.startsWith(resolve(config.uiRoot)+sep)) {res.writeHead(403);res.end();return;}
      const data=await readFile(file);
      res.writeHead(200,{'Content-Type':MIME[extname(file)]||'application/octet-stream','X-Content-Type-Options':'nosniff',
        'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; worker-src 'self' blob:; frame-ancestors 'self'; object-src 'none'"});
      res.end(data);
    } catch {res.writeHead(502);res.end('Triton service unavailable; inspect backend logs');}
  }}));
}
