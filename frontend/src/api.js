export async function request(path, { token, method = 'GET', body, signal } = {}) {
  const sessionAtStart = sessionContext;
  const response = await fetch(`/api${path}`, {
    method, signal, credentials: 'same-origin',
    headers: { ...(token && token !== 'session' ? { Authorization: `Bearer ${token}` } : {}),
      ...(sessionContext && method !== 'GET' ? { 'X-CSRF-Token': sessionContext.csrf_token } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (sessionAtStart !== sessionContext && !['/sessions','/session'].includes(path)) throw new DOMException('Session changed', 'AbortError');
  let data;
  try { data = await response.json(); } catch { throw new Error('未能连接本地任务 API，请检查服务与代理配置。'); }
  if (sessionAtStart !== sessionContext && !['/sessions','/session'].includes(path)) throw new DOMException('Session changed', 'AbortError');
  if (!response.ok || data.status !== 'ok') throw new Error(data.error?.message || `请求失败（${response.status}）`);
  return data.data;
}
export function downloadJson(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

let sessionContext = null;
export function setSessionContext(value) { sessionContext = value; }
export function currentSession() { return sessionContext; }
