// Pure, bounded CGA mapping. No Python execution, compiler or device is required.
// Semantics: Triton CGAEncodingAttr::fromSplitParams / permutation-matrix bases.
export const CGA_LIMITS = { rank: 4, bases: 8, ctas: 256, text: 16384 };
const fail = message => { throw new Error(message); };
const powerOfTwo = n => Number.isSafeInteger(n) && n >= 1 && n <= 256 && (n & (n - 1)) === 0;
const product = xs => xs.reduce((a, b) => a * b, 1);

function readArray(text, start) {
  if (text[start] !== '[') fail('需要 JSON 数组。');
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    if (text[i] === '[') depth++;
    if (text[i] === ']' && --depth === 0) {
      try { return JSON.parse(text.slice(start, i + 1)); } catch { fail('数组语法错误，请使用整数和英文逗号。'); }
    }
  }
  fail('数组缺少结束的 ]。');
}
function field(text, name) {
  const matches = [...text.matchAll(new RegExp(`\\b${name}\\s*=\\s*(\\[)`, 'gi'))];
  if (matches.length > 1) fail(`${name} 出现多次，请只粘贴一份布局。`);
  return matches.length ? readArray(text, matches[0].index + matches[0][0].lastIndexOf('[')) : null;
}
function rankCheck(rank) {
  if (!Number.isInteger(rank) || rank < 1 || rank > CGA_LIMITS.rank) fail('支持 1–4 维布局。');
}
export function legacyToBases(ctas, split, order) {
  if (![ctas, split, order].every(Array.isArray)) fail('旧格式需要 CTAsPerCGA、CTASplitNum 和 CTAOrder 三个数组。');
  const rank = ctas.length; rankCheck(rank);
  if (split.length !== rank || order.length !== rank) fail('三个数组的维数必须一致。');
  if (!ctas.every(powerOfTwo) || !split.every(powerOfTwo)) fail('CTA 数量与 split 必须是 1–256 内的 2 的幂。');
  if (split.some((n, i) => n > ctas[i] || ctas[i] % n !== 0)) fail('每维 split 必须整除且不大于 CTAsPerCGA。');
  if (new Set(order).size !== rank || !order.every(n => Number.isInteger(n) && n >= 0 && n < rank)) fail('CTAOrder 必须是全部维度编号的排列。');
  if (product(ctas) > CGA_LIMITS.ctas) fail('当前最多展示 256 个 CTA。');
  const bases = [];
  for (const dim of order) {
    for (let bit = 1; bit < split[dim]; bit *= 2) {
      const basis = Array(rank).fill(0); basis[dim] = bit; bases.push(basis);
    }
    for (let n = split[dim]; n < ctas[dim]; n *= 2) bases.push(Array(rank).fill(0));
  }
  return { bases, rank };
}
export function parseCgaLayout(source, emptyRank = 2) {
  if (typeof source !== 'string' || !source.trim()) fail('请输入 CGA layout。');
  if (source.length > CGA_LIMITS.text) fail('输入过长，请只保留布局片段（最多 16 KiB 字符）。');
  const text = source.trim();
  let bases, legacy, rank = emptyRank;
  if (text.startsWith('{')) {
    let obj;
    try { obj = JSON.parse(text); } catch { fail('JSON 格式错误。'); }
    if (obj?.kind === 'cga-layout' && obj.input) return parseCgaLayout(obj.input.layout, obj.input.rank);
    bases = obj.bases ?? obj.cga_layout ?? obj.CGALayout;
    if (obj.CTAsPerCGA !== undefined) legacy = legacyToBases(obj.CTAsPerCGA, obj.CTASplitNum, obj.CTAOrder);
    if (obj.rank !== undefined) rank = obj.rank;
  } else if (text.startsWith('[')) {
    try { bases = JSON.parse(text); } catch { fail('布局必须是完整的 JSON 二维数组。'); }
  } else {
    const mlir = field(text, 'CGALayout'), gluon = field(text, 'cga_layout');
    if (mlir !== null && gluon !== null) fail('检测到多个 CGA layout，请只粘贴一份布局。');
    bases = mlir ?? gluon;
    const ctas = field(text, 'CTAsPerCGA');
    if (ctas !== null) legacy = legacyToBases(ctas, field(text, 'CTASplitNum'), field(text, 'CTAOrder'));
  }
  if (bases !== undefined && bases !== null && legacy) fail('检测到两种布局定义，请只保留其中一种。');
  if (legacy) ({ bases, rank } = legacy);
  if (!Array.isArray(bases)) fail('未识别布局。输入 [[1,0],[0,1]]、CGALayout=… 或旧格式的三个数组。');
  if (bases.length > CGA_LIMITS.bases) fail('当前最多支持 8 个基向量（256 CTA）。');
  if (bases.length) rank = Array.isArray(bases[0]) ? bases[0].length : 0;
  rankCheck(rank);
  const occupied = new Set();
  const extents = Array(rank).fill(1);
  for (const basis of bases) {
    if (!Array.isArray(basis) || basis.length !== rank) fail('每个基向量必须有相同维数。');
    if (!basis.every(n => Number.isSafeInteger(n) && n >= 0 && n <= 128)) fail('基向量分量必须为 0–128 的整数。');
    const active = basis.map((n, dim) => ({ n, dim })).filter(v => v.n !== 0);
    if (active.length > 1 || active.some(v => !powerOfTwo(v.n))) fail('CGA 基向量只能是零向量，或仅一维为 2 的幂；任意 XOR/LinearEncoding 不属于此工具的 CGA tile 模型。');
    if (active.length) {
      const { n, dim } = active[0], key = `${dim}:${n}`;
      if (occupied.has(key)) fail('非零基向量重复，不符合 CGA permutation-matrix 约束。');
      occupied.add(key); extents[dim] = Math.max(extents[dim], n * 2);
    }
  }
  for (let dim = 0; dim < rank; dim++) {
    for (let bit = 1; bit < extents[dim]; bit *= 2) if (!occupied.has(`${dim}:${bit}`)) fail(`D${dim} 的基向量缺少 ${bit}，无法组成连续 CTA tile。`);
  }
  return { rank, bases: bases.map(b => [...b]), extents, format: legacy ? 'legacy' : 'linear' };
}
export function buildCgaLayout(source, emptyRank = 2, tileShape = null) {
  const parsed = parseCgaLayout(source, emptyRank);
  const shape = tileShape ?? Array(parsed.rank).fill(1);
  if (!Array.isArray(shape) || shape.length !== parsed.rank || !shape.every(n => Number.isSafeInteger(n) && n >= 1 && n <= 1048576)) fail(`Tile shape 需要 ${parsed.rank} 个 1–1048576 内的整数。`);
  const ctas = [], groups = new Map();
  for (let id = 0; id < 2 ** parsed.bases.length; id++) {
    const coord = Array(parsed.rank).fill(0);
    parsed.bases.forEach((basis, bit) => { if ((id >> bit) & 1) basis.forEach((n, dim) => { coord[dim] ^= n; }); });
    const key = coord.join(',');
    const cta = { id, coord, key, bits: id.toString(2).padStart(Math.max(1, parsed.bases.length), '0'), ranges: coord.map((n, dim) => [n * shape[dim], (n + 1) * shape[dim]]) };
    ctas.push(cta);
    if (!groups.has(key)) groups.set(key, { key, coord, owners: [] });
    groups.get(key).owners.push(id);
  }
  return { ...parsed, tileShape: shape, tensorShape: parsed.extents.map((n, i) => n * shape[i]), ctas, groups: [...groups.values()], ctaCount: ctas.length, tileCount: groups.size, replicas: ctas.length / groups.size };
}
export const CGA_PRESETS = [
  { id: 'grid', name: '2 × 2 切分', layout: '[[0, 1], [1, 0]]', rank: 2, tile: [64, 128] },
  { id: 'column', name: '沿列 4 CTA', layout: '[[0, 1], [0, 2]]', rank: 2, tile: [64, 64] },
  { id: 'replica', name: '切分 + 复制', layout: '[[1, 0], [0, 0], [0, 1]]', rank: 2, tile: [64, 128] },
  { id: 'cube', name: '3D · 8 CTA', layout: '[[0, 0, 1], [0, 1, 0], [1, 0, 0]]', rank: 3, tile: [16, 32, 64] },
  { id: 'single', name: '单 CTA', layout: '[]', rank: 2, tile: [64, 128] },
];
export function cgaExport(layout, source) {
  return { schema_version: 1, kind: 'cga-layout', source: 'local_layout_calculation', input: { layout: source, rank: layout.rank, tileShape: layout.tileShape }, result: layout };
}
