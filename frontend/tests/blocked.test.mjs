import test from 'node:test';
import assert from 'node:assert/strict';
import { buildBlockedLayout, parseBlockedShape, parseBlockedLayout, contiguousRuns } from '../src/tools/blocked-layout.js';
const layout = (spt=[2,4],tpw=[16,2],wpc=[2,2],order=[1,0],extra={}) => JSON.stringify({sizePerThread:spt,threadsPerWarp:tpw,warpsPerCTA:wpc,order,...extra});
const owners = (m,index) => m.cells[index].owners.map(o=>[o.thread,o.register]);
test('official BlockedLayout small tensor example preserves warp replication',()=>{
 const m=buildBlockedLayout('32, 8',layout());
 assert.deepEqual(m.baseTile,[64,16]); assert.equal(m.numRegisters,8);
 assert.deepEqual(owners(m,0),[[0,0],[32,0],[64,0],[96,0]]);
 assert.deepEqual(owners(m,7),[[1,3],[33,3],[65,3],[97,3]]);
 assert.deepEqual(owners(m,8),[[0,4],[32,4],[64,4],[96,4]]);
});
test('large tensor extends registers within same CTA',()=>{
 const m=buildBlockedLayout('256',layout([2],[32],[2],[0]));
 assert.equal(m.blocks.length,1); assert.equal(m.numRegisters,4);
 assert.deepEqual(m.threads[0].indices,[0,1,128,129]);
 assert.equal(m.cells.every(c=>c.owners.length===1),true);
});
test('order changes register and lane traversal',()=>{
 const a=buildBlockedLayout('4,4',layout([2,2],[2,2],[1,1],[1,0]));
 const b=buildBlockedLayout('4,4',layout([2,2],[2,2],[1,1],[0,1]));
 assert.deepEqual(owners(a,1),[[0,1]]); assert.deepEqual(owners(b,1),[[0,2]]);
 assert.deepEqual(owners(a,2),[[1,0]]); assert.deepEqual(owners(b,2),[[2,0]]);
});
test('small shape removes zero register bases but preserves replicated lanes',()=>{
 const m=buildBlockedLayout('1',layout([4],[32],[2],[0]));
 assert.equal(m.numRegisters,1); assert.equal(m.cells[0].owners.length,64);
});
test('CGA splits tensor coarsely and zero bases replicate CTA',()=>{
 const m=buildBlockedLayout('8,8',layout([1,1],[2,4],[1,1],[1,0],{CGALayout:[[1,0],[0,0]]}));
 assert.deepEqual(m.perCTA,[4,8]); assert.equal(m.blocks.length,4);
 assert.deepEqual(m.cells[0].owners.map(o=>o.block),[0,2]);
 assert.deepEqual(m.cells[32].owners.map(o=>o.block),[1,3]);
 const small=buildBlockedLayout('1,8',layout([1,1],[1,8],[1,1],[1,0],{CGALayout:[[1,0],[2,0]]}));
 assert.equal(small.cells[0].owners.length,4);
});
test('MLIR, named Gluon, positional Gluon and legacy CGA parse identically',()=>{
 const expected=buildBlockedLayout('4,8',layout([1,2],[2,4],[1,1],[1,0]));
 for(const text of ['#ttg.blocked<{sizePerThread=[1,2], threadsPerWarp=[2,4], warpsPerCTA=[1,1], order=[1,0]}>','gl.BlockedLayout(size_per_thread=[1,2], threads_per_warp=[2,4], warps_per_cta=[1,1], order=[1,0])','gl.BlockedLayout([1,2], [2,4], [1,1], [1,0])']) {
  assert.deepEqual(buildBlockedLayout('4x8',text).cells,expected.cells);
 }
 const text='gl.BlockedLayout([1,2], [2,4], [1,1], [1,0], [[1,0]])';
 assert.equal(buildBlockedLayout('4,8',text).blocks.length,2);
 assert.equal(buildBlockedLayout('4,8',layout([1,2],[2,4],[1,1],[1,0],{CTAsPerCGA:[2,1],CTASplitNum:[2,1],CTAOrder:[1,0]})).blocks.length,2);
});
test('coverage and ownership stay consistent across shapes and orders',()=>{
 for(const rows of [1,2,8,32]) for(const cols of [1,4,16]) for(const order of [[0,1],[1,0]]) {
  const m=buildBlockedLayout(`${rows},${cols}`,layout([2,2],[4,8],[2,1],order));
  assert.equal(m.cells.length,rows*cols); assert.ok(m.cells.every(c=>c.owners.length));
  assert.equal(m.cells.reduce((n,c)=>n+c.owners.length,0),m.ownerCount);
  for(const t of m.threads) for(const i of t.indices) assert.ok(m.cells[i].owners.some(o=>o.key===t.key));
 }
});
test('bounded input rejects unsupported shapes, layouts and replication',()=>{
 for(const shape of ['3,8','0','[8,8,8,8,8]','65536,2','NaN']) assert.throws(()=>parseBlockedShape(shape));
 for(const bad of [layout([1,1],[2,16],[1,1],[0,0]),layout([1],[32],[1],[0]),'#ttg.blocked<{sizePerThread=[1,1],threadsPerWarp=[2,16],warpsPerCTA=[1,1],order=[1,0],CGALayout=#cga}>','gl.SliceLayout(0, blocked)']) assert.throws(()=>parseBlockedLayout(bad,2));
 assert.throws(()=>buildBlockedLayout('1',layout([1],[128],[32],[0],{CGALayout:[[0],[0],[0],[0],[0]]})),/16 个 CTA/);
 assert.throws(()=>buildBlockedLayout('1,64',layout([1,1],[128,1],[32,1],[1,0],{CGALayout:[[0,0],[0,0]]})),/262144/)
});
test('continuity merges only adjacent row-major logical indices',()=>{
 assert.deepEqual(contiguousRuns([9,2,1,2,4,8]),[[1,2],[4,4],[8,9]]);
 assert.deepEqual(contiguousRuns([]),[]);
});

test('65536-element tensors preserve exact logical coverage',()=>{
 const m=buildBlockedLayout('256,256',layout([1,2],[2,16],[2,1],[1,0],{CGALayout:[[1,0]]}));
 assert.equal(m.cells.length,65536);assert.equal(m.ownerCount,65536);
 assert.deepEqual(m.cells[65535].coord,[255,255]);
 assert.equal(m.cells.every(c=>c.owners.length===1),true);
 assert.deepEqual(parseBlockedShape('65536'),[65536]);
});
