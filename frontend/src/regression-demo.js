// Browser-only illustrative replay. No SDK update, pytest execution, model API or backend request.
export const DEMO_STEPS = [
  ['baseline', '验证基线', '同一配置重复通过，才继续检查最新环境。'],
  ['update', '更新最新环境', '演示锁定最新SDK，后续搜索不再跟随latest漂移。'],
  ['latest', '验证最新版本', '最新环境出现同一目标故障，开始查找引入日期。'],
  ['search', '二分：10-14', '10-14通过，区间缩小到10-14～10-19。'],
  ['search', '二分：10-16', '10-16失败，区间缩小到10-14～10-16。'],
  ['search', '二分：10-15', '10-15失败，找到相邻好坏版本。'],
  ['audit_history', '确认最早失败', '补测10-11～10-13通过，排查更早回归。'],
  ['audit_boundary', '独立复验边界', '分别重复好、坏环境，确认结果稳定。'],
  ['components', '替换LLVM', '换入LLVM仍通过，回退LLVM仍失败，暂无双向支持。'],
  ['components', '替换cmodel', '新版换入失败、旧版回退通过，获得组件关联证据。'],
  ['complete', '生成报告', '展示搜索轨迹与组件矩阵；浏览器演示不构成真实定位证据。'],
];
const components = n => ({llvm:n,cmodel:n,torch:n});
const versions = Array.from({length:10},(_,i)=>({id:`mock-sdk-202610${10+i}`,date:`2026-10-${10+i}`,components:components(i),source:'browser_demo'}));
export const DEMO_CATALOG = {nodeid:'test_regression.py::test_regression[fp16]',versions,scenarios:[{id:'component',name:'单组件回归（浏览器演示）'}]};
export function regressionDemo(step = DEMO_STEPS.length - 1) {
  const cursor=Math.max(0,Math.min(DEMO_STEPS.length-1,Math.trunc(Number(step))||0));
  const record={schema_version:1,id:'browser-demo-regression',source:'browser_demo',state:cursor===10?'completed':'running',phase:DEMO_STEPS[cursor][0],result:cursor===10?'component_supported':null,
    spec:{scenario:'component',baseline:versions[0].id,repeats:2,max_experiments:60,max_seconds:600,max_model_calls:12,search_mode:'earliest_verified'},inventory:cursor>=1?versions:[],experiments:[],events:[],decisions:[],attribution:[],model_calls:0,elapsed_seconds:0,earliest_proven:false,boundary:null};
  function add(label,n,outcome,phase,group=components(n)) {
    const time=record.experiments.length+1;
    record.events.push({phase,time,message:`浏览器示意：${label} → ${outcome}`});
    for(let repeat=0;repeat<2;repeat++) record.experiments.push({id:`demo_exp_${String(record.experiments.length+1).padStart(3,'0')}`,label,components:group,repeat,classification:outcome,started_at:time+.1,finished_at:time+.1,returncode:outcome==='passed'?0:1,source:'browser_demo'});
  }
  add('baseline',0,'passed','baseline');
  if(cursor>=1) record.target=versions[9];
  if(cursor>=2) add('latest',9,'target_failure','latest');
  if(cursor>=3) add(versions[4].id,4,'passed','search');
  if(cursor>=4) add(versions[6].id,6,'target_failure','search');
  if(cursor>=5) {
    add(versions[5].id,5,'target_failure','search');
    record.boundary={good:versions[4],bad:versions[5],adjacent:true,earliest_proven:false};
  }
  if(cursor>=6) {
    [1,2,3].forEach(n=>add(versions[n].id,n,'passed','audit_history'));
    record.earliest_proven=true;record.boundary.earliest_proven=true;
  }
  if(cursor>=7) { add('audit_good',4,'passed','audit_boundary');add('audit_bad',5,'target_failure','audit_boundary'); }
  function intervene(name,forward,rollback) {
    add(`forward:${name}`,4,forward,'components',{...components(4),[name]:5});
    add(`rollback:${name}`,5,rollback,'components',{...components(5),[name]:4});
    record.attribution.push({components:[name],forward,rollback,supported:forward==='target_failure'&&rollback==='passed',scope:'browser_demo'});
    record.decisions.push({type:'select_candidate',candidate_id:name,reason_summary:`演示候选：${name}，非模型实际调用。`,evidence_ids:record.experiments.slice(-4).map(e=>e.id),source:'browser_demo'});
  }
  if(cursor>=8) intervene('llvm','passed','target_failure');
  if(cursor>=9) intervene('cmodel','target_failure','passed');
  record.supported_components=cursor===10?['cmodel']:[];
  return record;
}
export function demoEvidence(record,id) {
  const e=record.experiments.find(row=>row.id===id);
  if(!e) throw new Error('演示实验尚未发生。');
  return {id,classification:e.classification,source:'browser_demo',process:{returncode:e.returncode,stdout:`[浏览器流程示意，未执行pytest]\n${e.label}\n${e.classification==='passed'?'PASS（示意）':'FAIL（示意）：MOCK_REGRESSION'}\n此内容用于解释流程，不是实际运行日志。`,stderr:''},stages:[],observed_components:e.components,environment_sha256:'未采集（浏览器演示）'};
}
export function demoReport(record) {
  const markdown=`# 回归定位浏览器演示\n\n本报告是预设流程回放：未更新SDK、未运行pytest、未调用模型API，不作为实际故障证据。\n\n当前阶段：${record.phase}\n演示边界：${record.boundary?record.boundary.good.id+' → '+record.boundary.bad.id:'尚未展示'}\n演示组件结论：${record.supported_components.join(' + ')||'未确认'}\n\n连接本地服务后，可以启动真实CPU pytest的mock SDK调查并生成实际日志与可重放证据包。\n`;
  return {markdown,html:'<!doctype html><meta charset="utf-8"><title>浏览器流程演示</title><pre>'+markdown+'</pre>',record};
}
