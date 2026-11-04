import test from 'node:test';
import assert from 'node:assert/strict';
import {blockedScene,clampView,zoomAt,fitView,hitBlockedCell,cellIndex,visibleBlockedRange,facetLabel,TILE} from '../src/tools/blocked-view.js';
test('pointer anchored zoom preserves world position when away from bounds',()=>{
 const scene=blockedScene([256,256]),size={width:600,height:440};
 const v={zoom:.5,x:300,y:200},p={x:125,y:85},next=zoomAt(v,1.5,p,scene,size);
 assert.equal((v.x+p.x)/v.zoom,(next.x+p.x)/next.zoom);
 assert.equal((v.y+p.y)/v.zoom,(next.y+p.y)/next.zoom);
 assert.deepEqual(clampView({zoom:1,x:-1,y:1e9},scene,size),{zoom:1,x:0,y:scene.height-440});
});
test('hit testing inverts multi-dimensional cell positions and rejects gaps',()=>{
 for(const shape of [[8],[4,8],[4,8,2],[4,8,2,4]]) {
  const scene=blockedScene(shape),v={zoom:.7,x:8,y:3};
  for(let f=0;f<scene.facets;f++)for(let r=0;r<scene.rows;r++)for(let c=0;c<scene.cols;c++) {
   const point={x:(c*TILE.x+10)*v.zoom-v.x,y:(f*scene.facetHeight+scene.header+r*TILE.y+10)*v.zoom-v.y};
   assert.equal(hitBlockedCell(scene,v,point),cellIndex(scene,f,r,c));
  }
 }
 const s=blockedScene([4,8,2]);
 assert.equal(hitBlockedCell(s,{zoom:1,x:0,y:0},{x:0,y:0}),null);
 assert.equal(hitBlockedCell(s,{zoom:1,x:0,y:0},{x:64,y:40}),null);
 assert.equal(facetLabel(blockedScene([2,4,2,4]),5),'D2 = 1 · D3 = 1');
});
test('visible ranges cull offscreen rows, columns and high-dimensional facets',()=>{
 const scene=blockedScene([256,256]),size={width:600,height:440};
 const ranges=visibleBlockedRange(scene,{zoom:1,x:660,y:530},size);
 assert.equal(ranges.length,1);assert.equal(ranges[0].startCol,10);assert.equal(ranges[0].startRow,10);
 const drawn=ranges.reduce((n,r)=>n+(r.endCol-r.startCol+1)*(r.endRow-r.startRow+1),0);
 assert.ok(drawn<110); // Full tensor is 65536 elements.
 const facets=blockedScene([1,1,256,256]);
 assert.ok(visibleBlockedRange(facets,{zoom:1,x:0,y:10000},size).length<8);
});
test('overview fits large tensors while width fit and zoom bounds stay usable',()=>{
 const scene=blockedScene([256,256]),size={width:600,height:440};
 const fit=fitView(scene,size);assert.ok(scene.width*fit.zoom<=600);assert.ok(scene.height*fit.zoom<=440);
 assert.equal(fitView(scene,size,true).zoom,600/scene.width);
 assert.equal(zoomAt(fit,0,{x:0,y:0},scene,size).zoom,.00001);
 assert.equal(zoomAt(fit,20,{x:0,y:0},scene,size).zoom,4);
});
