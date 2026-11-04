// Bounded register/lane/warp/block -> logical tensor mapping for Triton BlockedLayout.
import { buildCgaLayout } from './cga-layout.js';
export const BLOCKED_LIMITS = { rank: 4, elements: 65536, owners: 262144, ctas: 16 };
const fail = message => { throw new Error(message); };
const product = xs => xs.reduce((a, b) => a * b, 1);
const power = n => Number.isSafeInteger(n) && n >= 1 && n <= 65536 && (n & (n - 1)) === 0;

export function parseBlockedShape(source) {
  if (typeof source !== 'string' || source.length > 256) fail('请输入 shape，例如 8, 16。');
  let shape;
  const text = source.trim();
  if (text.startsWith('[')) {
    try { shape = JSON.parse(text); } catch { fail('Shape 数组格式错误。'); }
  } else {
    if (!/^\d+(\s*[,x×]\s*\d+)*$/.test(text)) fail('Shape 使用正整数，以英文逗号或 x 分隔。');
    shape = text.split(/[,x×]/).map(Number);
  }
  if (!Array.isArray(shape) || shape.length < 1 || shape.length > BLOCKED_LIMITS.rank || !shape.every(power)) fail('逻辑 tensor shape 支持 1–4 维，每维必须是 1–65536 内的 2 的幂。');
  if (product(shape) > BLOCKED_LIMITS.elements) fail('最多展示 65536 个元素，请缩小 shape。');
  return shape;
}
function arrayAt(text, index) {
  let depth = 0;
  for (let i = index; i < text.length; i++) {
    if (text[i] === '[') depth++;
    if (text[i] === ']' && --depth === 0) {
      try { return { value: JSON.parse(text.slice(index, i + 1)), end: i + 1 }; } catch { fail('布局数组只能包含整数。'); }
    }
  }
  fail('布局数组缺少结束的 ]。');
}
function named(text, aliases) {
  const matches = [...text.matchAll(new RegExp(`\\b(?:${aliases.join('|')})\\s*=\\s*(\\[)`, 'g'))];
  if (matches.length > 1) fail(`${aliases[0]} 重复，请只输入一份布局。`);
  return matches.length ? arrayAt(text, matches[0].index + matches[0][0].lastIndexOf('[')).value : undefined;
}
const FIELDS = { sizePerThread: ['sizePerThread','size_per_thread'], threadsPerWarp: ['threadsPerWarp','threads_per_warp'], warpsPerCTA: ['warpsPerCTA','warps_per_cta'], order: ['order'] };
export function parseBlockedLayout(source, rank) {
  if (typeof source !== 'string' || !source.trim() || source.length > 16384) fail('请输入单份 BlockedLayout（最多16384字符）。');
  const text = source.trim(), out = {};
  let cga;
  if (text.startsWith('{')) {
    let obj;
    try { obj = JSON.parse(text); } catch { fail('布局 JSON 格式错误。'); }
    const known = [...Object.values(FIELDS).flat(),'CGALayout','cga_layout','CTAsPerCGA','CTASplitNum','CTAOrder'];
    if (Object.keys(obj).some(k => !known.includes(k))) fail('JSON 含不支持的布局字段。');
    for (const [key, aliases] of Object.entries(FIELDS)) {
      const present = aliases.filter(k => Object.hasOwn(obj,k));
      if (present.length > 1) fail(`${key} 重复。`);
      out[key] = obj[present[0]];
    }
    if (obj.CGALayout !== undefined && obj.cga_layout !== undefined) fail('CGA 布局重复。');
    cga = obj.CGALayout ?? obj.cga_layout;
    if (obj.CTAsPerCGA !== undefined || obj.CTASplitNum !== undefined || obj.CTAOrder !== undefined) {
      if (cga !== undefined) fail('请只保留一种 CGA 格式。');
      cga = { CTAsPerCGA: obj.CTAsPerCGA, CTASplitNum: obj.CTASplitNum, CTAOrder: obj.CTAOrder };
    }
  } else {
    if (/slice|dot_op|nvidia_mma|swizzled|LinearEncoding|SliceLayout|MmaLayout/i.test(text)) fail('这里只支持普通 BlockedLayout，不支持 Slice、MMA 或 swizzled 布局。');
    if ((text.match(/BlockedLayout\s*\(/g) || []).length > 1 || (text.match(/#(?:ttg|triton_gpu)\.blocked\s*</g) || []).length > 1) fail('请只输入一份 BlockedLayout。');
    for (const [key, aliases] of Object.entries(FIELDS)) out[key] = named(text,aliases);
    const a = named(text,['CGALayout']), b = named(text,['cga_layout']);
    if (a !== undefined && b !== undefined) fail('CGA 布局重复。');
    cga = a ?? b;
    const total = named(text,['CTAsPerCGA']), split = named(text,['CTASplitNum']), order = named(text,['CTAOrder']);
    if (total !== undefined || split !== undefined || order !== undefined) {
      if (cga !== undefined) fail('请只保留一种 CGA 格式。');
      cga = { CTAsPerCGA: total, CTASplitNum: split, CTAOrder: order };
    }
    const positional = text.match(/\bBlockedLayout\s*\(\s*(?=\[)/);
    if (positional) {
      if (Object.values(out).some(v => v !== undefined)) fail('请不要混用位置参数和具名基础参数。');
      let cursor = positional.index + positional[0].length;
      for (const key of Object.keys(FIELDS)) {
        if (text[cursor] !== '[') fail('BlockedLayout 需要四个基础数组参数。');
        const arr = arrayAt(text,cursor); out[key] = arr.value;
        cursor = arr.end;
        while (/[\s,]/.test(text[cursor] || '\0')) cursor++;
      }
      if (text[cursor] === '[') {
        if (cga !== undefined) fail('CGA 布局重复。');
        const arr = arrayAt(text,cursor); cga = arr.value; cursor = arr.end;
      }
      const rest = text.slice(cursor).trim();
      if (!/^(?:\)|(?:cga_layout|CGALayout)\s*=)/.test(rest)) fail('存在不支持的位置参数或表达式。');
    }
    // Do not silently turn a referenced/unknown CGA layout into a single CTA.
    if (cga === undefined && /\b(?:CGALayout|cga_layout|CTALayout)\s*=/.test(text)) fail('CGA 布局引用无法解析，请内联基向量或旧三参数。');
  }
  for (const [key,value] of Object.entries(out)) {
    if (!Array.isArray(value) || value.length !== rank) fail(`${key} 需要与 shape 相同的 ${rank} 维数组。`);
    if (key !== 'order' && !value.every(n => power(n) && n <= 4096)) fail(`${key} 各项必须是 1–4096 内的 2 的幂。`);
  }
  if (new Set(out.order).size !== rank || !out.order.every(n => Number.isInteger(n) && n >= 0 && n < rank)) fail('order 必须是所有维度的排列，最快维在前。');
  if (product(out.threadsPerWarp) > 128 || product(out.warpsPerCTA) > 32) fail('展示上限为每 warp 128 lane、每 CTA 32 warp。');
  const cgaModel = buildCgaLayout(JSON.stringify(cga === undefined ? {bases:[],rank} : Array.isArray(cga) ? {bases:cga,rank} : cga),rank);
  if (cgaModel.rank !== rank) fail('CGA 布局维数必须与 shape 相同。');
  if (cgaModel.ctaCount > BLOCKED_LIMITS.ctas) fail('当前最多展示 16 个 CTA。');
  return { ...out, cga: cgaModel };
}
function orderedBits(sizes, order, scales) {
  const bits = [];
  for (const dim of order) for (let n = 1; n < sizes[dim]; n *= 2) {
    const basis = Array(sizes.length).fill(0); basis[dim] = n * scales[dim]; bits.push(basis);
  }
  return bits;
}
function applyBits(value, bases, rank) {
  const coords = Array(rank).fill(0);
  bases.forEach((basis, bit) => { if ((value >> bit) & 1) basis.forEach((n,d) => { coords[d] ^= n; }); });
  return coords;
}
export function buildBlockedLayout(shapeSource, layoutSource) {
  const shape = parseBlockedShape(shapeSource), rank = shape.length, layout = parseBlockedLayout(layoutSource,rank);
  const split = layout.cga.extents.map((n,d) => Math.min(n,shape[d]));
  const perCTA = shape.map((n,d) => n / split[d]);
  const spt = layout.sizePerThread, tpw = layout.threadsPerWarp, wpc = layout.warpsPerCTA;
  const warpShape = spt.map((n,d) => n * tpw[d]), baseTile = warpShape.map((n,d) => n * wpc[d]);
  // Fit the CTA layout: excess lane/warp bits broadcast; zero register bits disappear.
  const trim = basis => basis.map((n,d) => n < perCTA[d] ? n : 0);
  const registerBits = orderedBits(spt,layout.order,Array(rank).fill(1)).map(trim).filter(b => b.some(Boolean));
  for (const d of layout.order) for (let n = baseTile[d]; n < perCTA[d]; n *= 2) {
    const basis = Array(rank).fill(0); basis[d] = n; registerBits.push(basis);
  }
  const laneBits = orderedBits(tpw,layout.order,spt).map(trim);
  const warpBits = orderedBits(wpc,layout.order,warpShape).map(trim);
  const numRegisters = 2 ** registerBits.length, numLanes = product(tpw), numWarps = product(wpc);
  const ownerCount = numRegisters * numLanes * numWarps * layout.cga.ctaCount;
  if (ownerCount > BLOCKED_LIMITS.owners) fail('布局的复制/寄存器映射超过262144条，请缩小shape、warp或CTA数量。');
  const cells = Array.from({length:product(shape)}, (_,index) => {
    const coord = Array(rank); let remaining = index;
    for (let d = rank - 1; d >= 0; d--) { coord[d] = remaining % shape[d]; remaining = Math.floor(remaining / shape[d]); }
    return { index, coord, owners: [] };
  });
  const threads = new Map(), blocks = new Map();
  for (const cta of layout.cga.ctas) {
    const offset = cta.coord.map((n,d) => (n % split[d]) * perCTA[d]);
    blocks.set(cta.id,{id:cta.id,indices:new Set()});
    for (let warp = 0; warp < numWarps; warp++) for (let lane = 0; lane < numLanes; lane++) {
      const thread = warp * numLanes + lane, key = `${cta.id}:${thread}`;
      const record = { key, block:cta.id, thread, indices:[] }; threads.set(key,record);
      const warpCoord = applyBits(warp,warpBits,rank), laneCoord = applyBits(lane,laneBits,rank);
      for (let register = 0; register < numRegisters; register++) {
        const regCoord = applyBits(register,registerBits,rank);
        const coord = offset.map((n,d) => n + (warpCoord[d] ^ laneCoord[d] ^ regCoord[d]));
        const index = coord.reduce((n,c,d) => n * shape[d] + c,0);
        const owner = {block:cta.id,warp,lane,thread,register,key};
        cells[index].owners.push(owner); record.indices.push(index); blocks.get(cta.id).indices.add(index);
      }
    }
  }
  if (cells.some(c => !c.owners.length)) fail('布局未覆盖全部元素。');
  for (const thread of threads.values()) thread.indices.sort((a,b)=>a-b);
  return { shape, layout, cells, threads:[...threads.values()], blocks:[...blocks.values()].map(b=>({...b,indices:[...b.indices].sort((a,b)=>a-b)})), perCTA, baseTile, numLanes, numWarps, numRegisters, ownerCount };
}
export function contiguousRuns(indices) {
  const result=[];
  for (const index of [...new Set(indices)].sort((a,b)=>a-b)) {
    const last=result[result.length-1];
    if (last && last[1]+1===index) last[1]=index;
    else result.push([index,index]);
  }
  return result;
}
