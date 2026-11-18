import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
import { routeName } from '../src/protocol.js';
const catalog=JSON.parse(execFileSync('../.venv/bin/python',['-m','triton_dev.harness','--catalog'],{cwd:process.cwd(),encoding:'utf8'}));
const names=[...catalog.commands.map(c=>c.name),...catalog.routes.map(routeName),'triton_open_page','triton_layout_cga','triton_layout_blocked'];
await build({entryPoints:['src/client.jsx'],outfile:'lib/client.js',bundle:true,format:'cjs',platform:'browser',external:['react'],define:{TOOL_NAMES:JSON.stringify(names)},
 banner:{js:'window.__ModuleLoader__.load({id:"triton-dev-harness",factory:(require)=>{var module={exports:{}};var exports=module.exports;'},
 footer:{js:'return module.exports;}});'}});
