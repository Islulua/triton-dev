export const DEMO_DATE = '2026-10-23';
export const SDKS = [
  { id: '1022', label: 'TX82 daily (2026-10-22)', python: '3.10.13', size: '1.24 GB', sha: '74c6af2e…d159', source: '演示制品' },
  { id: '1023', label: 'TX82 daily (2026-10-23)', python: '3.10.13', size: '1.26 GB', sha: '8b0d7c41…ac82', source: '演示制品' },
];
export const INITIAL_ENVIRONMENTS = [
  { name: 'baseline', description: '稳定基线环境', sdk: '1022', python: '3.10.13', triton: '1022', torch: '1022', status: 'imported', date: '2026-10-22', time: '14:21' },
  { name: 'nightly-1023', description: '最新构建验证', sdk: '1023', python: '3.10.13', triton: '1023', torch: '1023', status: 'imported', date: DEMO_DATE, time: '10:05' },
  { name: 'triton-candidate', description: '候选版本评估', sdk: '1022', python: '3.10.13', triton: '1023', torch: '1022', status: 'unverified', date: '2026-10-22', time: '18:30' },
  { name: 'torch-compare', description: '对比不同的 Torch 版本', sdk: '1022', python: '3.10.13', triton: '1022', torch: '1023', status: 'imported', date: '2026-10-22', time: '16:12' },
  { name: 'minimal-repro', description: '最小复现环境', sdk: '1023', python: '3.10.13', triton: '1023', torch: '1023', status: 'unverified', date: DEMO_DATE, time: '09:41' },
];
export const CASES = [
  { id: 'add', name: 'test_add[fp16]', params: 'dtype=fp16, M=1024', tag: 'elementwise', result: 'passed', fixture: 'device, input_tensors' },
  { id: 'matmul', name: 'test_matmul[128x128]', params: 'M=128, N=128, K=128', tag: 'matmul', result: 'failed', fixture: 'device, input_tensors, reference' },
  { id: 'reduce', name: 'test_reduce[axis=1]', params: 'axis=1, shape=(32,1024)', tag: 'reduction', result: 'passed', fixture: 'device, input_tensors' },
  { id: 'gather', name: 'test_gather[int32]', params: 'dtype=int32, vocab=4096', tag: 'indexing', result: 'passed', fixture: 'device, indices' },
  { id: 'transpose', name: 'test_transpose[32x64]', params: 'M=32, N=64', tag: 'layout', result: 'passed', fixture: 'device, input_tensors' },
  { id: 'softmax', name: 'test_softmax[fp32]', params: 'axis=-1, shape=(8,1024)', tag: 'reduction', result: 'passed', fixture: 'device, reference' },
  { id: 'layernorm', name: 'test_layernorm[fp16]', params: 'normalized_shape=1024', tag: 'normalization', result: 'passed', fixture: 'device, reference' },
];
export const INITIAL_RUNS = [
  { id: 'run_0183', name: 'correctness-check', state: 'failed', env: 'baseline', snapshot: { ...INITIAL_ENVIRONMENTS[0] }, caseIds: ['add', 'matmul', 'reduce'], failedIds: ['matmul'], params: { M: 128, N: 128 }, date: DEMO_DATE, time: '10:32', elapsed: '31.0s', source: 'demo' },
  { id: 'run_0182', name: 'smoke-test', state: 'passed', env: 'baseline', snapshot: { ...INITIAL_ENVIRONMENTS[0] }, caseIds: ['add', 'reduce'], failedIds: [], params: { M: 128, N: 128 }, date: '2026-10-22', time: '16:40', elapsed: '12.4s', source: 'demo' },
];
export function freshState() {
  return structuredClone({ schema: 1, environments: INITIAL_ENVIRONMENTS, runs: INITIAL_RUNS });
}
export function loadState(storage) {
  try {
    const state = JSON.parse(storage.getItem('triton-dev-ui-v1'));
    if (state?.schema === 1 && Array.isArray(state.environments) && Array.isArray(state.runs)
      && state.environments.every(e => typeof e.name === 'string' && SDKS.some(s => s.id === e.sdk))
      && state.runs.every(r => typeof r.id === 'string' && Array.isArray(r.caseIds) && Array.isArray(r.failedIds))) {
      return { ...state, environments: state.environments.map(e => ({ ...e, status: e.status === 'preparing' ? 'unverified' : e.status })),
        runs: state.runs.map(r => ({ ...r, state: ['queued', 'running'].includes(r.state) ? 'interrupted' : r.state })) };
    }
  } catch { /* Unavailable or invalid local storage falls back to a demo state. */ }
  return freshState();
}
export function validateCombination(draft, environments) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(draft.name)) return '组合名称需为 1–64 位字母、数字、下划线或连字符。';
  if (environments.some(e => e.name === draft.name)) return '该名称已存在。组合不可覆盖，请使用新名称。';
  if (![draft.sdk, draft.triton, draft.torch].every(id => SDKS.some(s => s.id === id))) return '请选择有效的制品版本。';
  return '';
}
export function validateParams(params) {
  return Object.values(params).every(v => Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 16384)
    ? '' : 'M、N 必须是 1–16384 之间的整数。';
}
export function combinationDiff(a, b) {
  return [ ['基础 SDK', a.sdk, b.sdk], ['Triton wheel', a.triton, b.triton], ['Torch wheel', a.torch, b.torch], ['Python', a.python, b.python] ]
    .map(([field, left, right]) => ({ field, left, right, changed: left !== right }));
}
export function demoFailure(caseIds, params) {
  return caseIds.includes('matmul') && Number(params.M) >= 128 ? ['matmul'] : [];
}
export const sdkLabel = id => SDKS.find(s => s.id === id)?.label || id;
export const tritonLabel = id => `triton-3.5.1.dev2026${id}+tx82`;
export const torchLabel = id => `torch_raisa-2.7.0.dev2026${id}`;
export function normalizeTask(record) {
  return { id: record.id, name: record.job_id || record.request?.argv?.slice(0, 2).map(value => value.split('/').at(-1)).join(' ') || '登记任务', state: record.state,
    date: record.created_at ? new Date(record.created_at * 1000).toLocaleDateString('sv') : '—',
    time: record.created_at ? new Date(record.created_at * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '—',
    elapsed: record.finished_at && record.started_at ? `${(record.finished_at - record.started_at).toFixed(1)}s` : '—',
    source: 'api', caseIds: [], failedIds: [], record, env: '登记配置' };
}
