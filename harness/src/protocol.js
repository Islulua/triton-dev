export const PAGES = ['daily','home','env','kernel','tools','tools-cga','tools-blocked','runs','reports','profiling','diagnosis','data','regression','models','settings'];
export function navigation(page, selection = {}) {
  if (!PAGES.includes(page)) throw new Error('Unknown Triton page');
  if (!selection || typeof selection !== 'object' || Array.isArray(selection)) throw new Error('selection must be an object');
  if (JSON.stringify(selection).length > 65536) throw new Error('selection too large');
  return {page, selection, issued_at: Date.now()};
}
export function routeName(route) {
  return 'triton_api_' + route.method.toLowerCase() + '_' + route.path.replace(/^\/api\//, '').replace(/[{}]/g, '').replace(/[^a-zA-Z0-9]+/g,'_');
}
export function routePath(route, params = {}, query = {}) {
  const path = route.path.replace(/\{([^}]+)\}/g, (_, key) => {
    const value = params[key];
    if (typeof value !== 'string' || !value || ['.','..'].includes(value) || /[\/\\]/.test(value)) throw new Error('Invalid path parameter: '+key);
    return encodeURIComponent(value);
  });
  const suffix = new URLSearchParams(query).toString();
  return path + (suffix ? '?'+suffix : '');
}
export function pageFor(path) {
  if (path.includes('/profiling')) return 'profiling';
  if (path.includes('/regression')) return 'regression';
  if (path.includes('/daily')) return 'daily';
  if (path.includes('/ir/')) return 'kernel';
  if (path.includes('ai-profiles')) return 'models';
  if (path.includes('sdk')) return 'env';
  if (path.includes('/data/') || path.includes('case-results')) return 'data';
  return 'runs';
}

// Stable page identities are shared by manual navigation and AI result navigation.
export const MODULES = [
  ['home','工作台'], ['daily','Daily'], ['env','环境与制品'], ['runs','用例与运行'],
  ['reports','测试报告'], ['profiling','Profiling'], ['regression','回归定位'],
  ['diagnosis','诊断与证据'], ['kernel','Kernel Lab'], ['tools','Tools'],
  ['tools-cga','CGA Layout'], ['tools-blocked','Blocked Layout'], ['data','数据中心'],
  ['models','Triton 模型配置'], ['settings','工具连接设置'],
].map(([page,title]) => ({page,title,kind:'triton-'+page,id:'triton-dev-harness/'+page,
  showInGuide:!['models','settings'].includes(page)}));
export function moduleFor(page) { return MODULES.find(module=>module.page===page); }
