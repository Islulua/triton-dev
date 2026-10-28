// All line numbers in the document model are 1-based physical/source locations.
const positive = value => Number.isSafeInteger(value) && value > 0;
export function normalizeIRDocument(value) {
  if (!value || typeof value !== 'object' || !value.source || typeof value.source.code !== 'string' || !Array.isArray(value.stages) || !value.stages.length) throw new Error('文件缺少源码或 IR 阶段');
  const source = { ...value.source, start_line: positive(value.source.start_line) ? value.source.start_line : 1 };
  if (source.file_path !== undefined && (typeof source.file_path !== 'string' || !source.file_path)) throw new Error('源码路径必须是非空文字');
  source.file_path ||= 'kernel.py';
  const metadata = value.metadata && typeof value.metadata === 'object' && !Array.isArray(value.metadata) ? { ...value.metadata } : {};
  for (const key of ['name', 'hash', 'backend', 'compiler_id']) if (typeof metadata[key] !== 'string') delete metadata[key];
  if (metadata.target && typeof metadata.target.backend !== 'string') delete metadata.target;
  const sourceEnd = source.start_line + source.code.split('\n').length - 1;
  const seen = new Set();
  const stages = value.stages.filter(s => s && typeof s.id === 'string' && typeof s.content === 'string').map(stage => {
    if (seen.has(stage.id)) throw new Error('IR 阶段 ID 重复');
    seen.add(stage.id);
    const lines = stage.content.split('\n').length, mapping = {};
    for (const [key, loc] of Object.entries(stage.mapping || {})) {
      if (!/^[1-9]\d*$/.test(key) || +key > lines || !loc || loc.file !== source.file_path || !positive(loc.line) || loc.line < source.start_line || loc.line > sourceEnd) continue;
      mapping[key] = { file: loc.file, line: loc.line, column: Number.isSafeInteger(loc.column) && loc.column >= 0 ? loc.column : 0 };
    }
    return { ...stage, label: typeof stage.label === 'string' ? stage.label : stage.id.toUpperCase(), mapping, mapping_status: Object.keys(mapping).length ? 'available' : 'unavailable' };
  });
  if (!stages.length) throw new Error('文件中没有可显示的 IR');
  return { ...value, schema_version: 1, source, stages, metadata, kernel: typeof value.kernel === 'string' ? value.kernel : metadata.name || 'kernel', source_kind: value.source_kind || 'imported' };
}
export function sameSource(a, b) { return !!a && !!b && a.code === b.code && a.file_path === b.file_path && a.start_line === b.start_line; }
export function needsCompilation(current, baseline) { return ['code', 'spec', 'entry', 'compiler'].some(key => current[key] !== baseline[key]); }
export function linkedLines(doc, stageId, selection) {
  if (!selection || !doc) return [];
  const mapping = doc.stages.find(s => s.id === stageId)?.mapping || {};
  return Object.entries(mapping).filter(([, loc]) => loc.file === selection.file && loc.line === selection.line).map(([line]) => +line);
}
export function acceptCompileResult(current, completed) {
  return current.revision === completed.revision && current.request === completed.request;
}
export function parseTraceText(text) {
  let entries;
  try { const parsed = JSON.parse(text); entries = Array.isArray(parsed) ? parsed : [parsed]; }
  catch { entries = text.trim().split('\n').map(line => JSON.parse(line)); }
  const docs = [];
  for (const entry of entries) {
    if (entry?.source && entry?.stages) { docs.push(normalizeIRDocument({ ...entry, source_kind: entry.source_kind === 'illustrative' ? 'illustrative' : 'imported' })); continue; }
    const payload = entry?.payload;
    if (!payload?.python_source || !payload?.file_content) continue;
    const stages = Object.entries(payload.file_content).filter(([name, content]) => typeof content === 'string' && !/\.(json|so|cubin|hsaco)$/.test(name)).map(([name, content]) => {
      const id = name.split('.').pop();
      return { id, label: payload.ir_stages?.find(s => s.name === id)?.display_name || id.toUpperCase(), content, mapping: Object.fromEntries(Object.entries(payload.source_mappings?.[id] || {}).map(([line, loc]) => [line, {
        file: loc.inlined_at_file || loc.file, line: loc.inlined_at_line ?? loc.line, column: loc.column,
      }])) };
    });
    if (stages.length) docs.push(normalizeIRDocument({ source: payload.python_source, stages, metadata: entry.metadata || {}, source_kind: 'imported', kernel: entry.metadata?.name }));
  }
  if (!docs.length) throw new Error('未找到含内嵌源码与 IR 的编译记录；原始 trace 可连接服务后导入解析');
  return docs;
}
