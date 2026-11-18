export function harnessSelection(location = globalThis.window?.location || {search:''}) {
  try {
    const value=JSON.parse(new URLSearchParams(location.search).get('selection')||'{}');
    return value && typeof value==='object' && !Array.isArray(value) ? value : {};
  } catch {return {};}
}
export function harnessHeaders(location = globalThis.window?.location || {search:''}) {
  const session=new URLSearchParams(location.search).get('harness_session');
  return session?{'X-Triton-Session':session}:{};
}
export function apiBase() {return `${(import.meta.env?.BASE_URL || "/")}api`;}

export function isHarnessEmbedded(location = globalThis.window?.location || {search:''}) {
  const params=new URLSearchParams(location.search);
  return params.get('embedded')==='1' && !!params.get('harness_session');
}
export function navigateInHarness(page, browser = globalThis.window) {
  if(!browser || !isHarnessEmbedded(browser.location) || browser.parent===browser)return false;
  browser.parent.postMessage({type:'triton:navigate',page},browser.location.origin);
  return true;
}
