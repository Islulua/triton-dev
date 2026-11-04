import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCgaLayout, parseCgaLayout, legacyToBases, CGA_PRESETS, cgaExport } from '../src/tools/cga-layout.js';

test('official CTA bases map low-to-high ID bits to contiguous tile coordinates', () => {
  const m = buildCgaLayout('[[1,0],[2,0],[0,1]]', 2, [32,64]);
  assert.equal(m.ctaCount, 8); assert.equal(m.tileCount, 8);
  assert.deepEqual(m.extents, [4,2]);
  assert.deepEqual(m.ctas.map(c => c.coord), [[0,0],[1,0],[2,0],[3,0],[0,1],[1,1],[2,1],[3,1]]);
  assert.deepEqual(m.ctas[6].ranges, [[64,96],[64,128]]);
  assert.deepEqual(m.tensorShape, [128,128]);
});
test('CTAOrder changes numbering while zero bases replicate data', () => {
  const row = buildCgaLayout('[[0,1],[1,0]]'), col = buildCgaLayout('[[1,0],[0,1]]');
  assert.deepEqual(row.extents, col.extents);
  assert.deepEqual(row.ctas[1].coord, [0,1]); assert.deepEqual(col.ctas[1].coord, [1,0]);
  const m = buildCgaLayout('[[1,0],[0,0],[0,1]]');
  assert.equal(m.replicas, 2); assert.equal(m.tileCount, 4);
  assert.deepEqual(m.groups.find(g => g.key === '1,0').owners, [1,3]);
});
test('legacy conversion preserves identity-then-broadcast bits in each CTAOrder dimension', () => {
  assert.deepEqual(legacyToBases([4,2], [2,2], [0,1]).bases, [[1,0],[0,0],[0,1]]);
  const m = buildCgaLayout('CTAsPerCGA = [4,2], CTASplitNum = [2,2], CTAOrder = [0,1]');
  assert.deepEqual(m.ctas[2].coord, [0,0]); assert.deepEqual(m.ctas[4].coord, [0,1]);
  const json = buildCgaLayout(JSON.stringify({ CTAsPerCGA: [4,2], CTASplitNum: [2,2], CTAOrder: [0,1] }));
  assert.deepEqual(json.ctas, m.ctas);
});
test('empty, broadcast, and four-dimensional layouts preserve rank and ownership', () => {
  const single = buildCgaLayout('[]', 3, [16,32,64]);
  assert.deepEqual(single.extents, [1,1,1]); assert.equal(single.ctaCount, 1);
  const broadcast = buildCgaLayout('[[0],[0],[0]]', 1, [64]);
  assert.equal(broadcast.ctaCount, 8); assert.equal(broadcast.tileCount, 1);
  assert.deepEqual(broadcast.groups[0].owners, [0,1,2,3,4,5,6,7]);
  const m = buildCgaLayout('[[0,0,0,1],[1,0,0,0],[0,1,0,0],[0,0,1,0]]');
  assert.equal(m.rank, 4); assert.equal(m.tileCount,16);
  assert.equal(m.groups.filter(g => g.coord[2] === 1 && g.coord[3] === 0).length,4);
  assert.deepEqual(m.ctas[15].coord,[1,1,1,1]);
});
test('MLIR and Gluon fragments extract their CGA field without executing code', () => {
  assert.deepEqual(parseCgaLayout('gl.BlockedLayout([1,1],[1,32],[1,4],[1,0], cga_layout=[[1,0]])').bases, [[1,0]]);
  assert.deepEqual(parseCgaLayout('#ttg.blocked<{order=[1,0], CGALayout = [[0,1]]}>').bases, [[0,1]]);
  assert.throws(() => parseCgaLayout('alert(1)'), /未识别/);
  assert.throws(() => parseCgaLayout('cga_layout=[[1,0]] cga_layout=[[0,1]]'), /多次/);
  assert.throws(() => parseCgaLayout('[[1, 0]]; alert(1)'), /完整/);
  assert.throws(() => parseCgaLayout('[[1e309, 0]]'), /整数/);
});
test('reject unsupported linear bases, dimension errors and exponential inputs', () => {
  for (const source of ['[[1,1]]','[[3,0]]','[[1,0],[1,0]]','[[2,0]]','[[1,0],[0]]','[[-1,0]]','[[0,0,0,0,1]]']) assert.throws(() => buildCgaLayout(source));
  assert.throws(() => buildCgaLayout(JSON.stringify(Array.from({length:9},()=>[0,0]))), /最多/);
  assert.throws(() => buildCgaLayout('[[1,0]]',2,[64]), /Tile shape/);
  assert.throws(() => legacyToBases([2,2],[4,1],[0,1]), /整除/);
  assert.throws(() => legacyToBases([3,2],[1,1],[0,1]), /2 的幂/);
  assert.throws(() => legacyToBases([2,2],[2,2],[1,1]), /排列/);
  assert.throws(() => legacyToBases([256,2],[1,1],[0,1]), /最多/);
});
test('presets and JSON export preserve provenance and every CTA exactly once', () => {
  for (const p of CGA_PRESETS) {
    const m = buildCgaLayout(p.layout,p.rank,p.tile), exported = cgaExport(m,p.layout);
    assert.equal(exported.source,'local_layout_calculation');
    assert.deepEqual(parseCgaLayout(JSON.stringify(exported)).bases,m.bases);
    assert.deepEqual(m.groups.flatMap(g=>g.owners).sort((a,b)=>a-b),m.ctas.map(c=>c.id));
  }
});

test('legacy mappings agree with ordered CTA coordinates across power-of-two split/replica combinations', () => {
  const orders = [[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]];
  for (const a of [1,2,4]) for (const b of [1,2,4]) for (const c of [1,2,4]) {
    const total = [a,b,c]; if (a*b*c > 16) continue;
    for (const x of [1,2,4].filter(n=>n<=a)) for (const y of [1,2,4].filter(n=>n<=b)) for (const z of [1,2,4].filter(n=>n<=c)) for (const order of orders) {
      const split=[x,y,z];
      const m=buildCgaLayout(JSON.stringify({CTAsPerCGA:total,CTASplitNum:split,CTAOrder:order}));
      for (const cta of m.ctas) {
        let remaining=cta.id; const expected=[0,0,0];
        for (const dim of order) { expected[dim]=(remaining % total[dim]) % split[dim]; remaining=Math.floor(remaining/total[dim]); }
        assert.deepEqual(cta.coord,expected);
      }
    }
  }
  assert.throws(()=>parseCgaLayout('CGALayout=[[1,0]] cga_layout=[[0,1]]'),/多个/);
});
