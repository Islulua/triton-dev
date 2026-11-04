// Geometry stays independent of React/Canvas so zoom and hit testing share one model.
export const TILE = { x:66, y:53, width:62, height:49 };
export const MIN_ZOOM = 0.00001;
export const MAX_ZOOM = 4;
export function blockedScene(shape) {
  const cols=shape.length===1?shape[0]:shape[1], rows=shape.length===1?1:shape[0];
  const facets=shape.slice(2).reduce((n,x)=>n*x,1), header=shape.length>2?28:0;
  const facetHeight=header+rows*TILE.y+20;
  return {shape,cols,rows,facets,header,facetHeight,width:cols*TILE.x,height:facets*facetHeight-20};
}
export function clampView(view,scene,size) {
  const zoom=Math.min(MAX_ZOOM,Math.max(MIN_ZOOM,view.zoom));
  return {zoom,x:Math.min(Math.max(0,view.x),Math.max(0,scene.width*zoom-size.width)),y:Math.min(Math.max(0,view.y),Math.max(0,scene.height*zoom-size.height))};
}
export function zoomAt(view,nextZoom,point,scene,size) {
  const zoom=Math.min(MAX_ZOOM,Math.max(MIN_ZOOM,nextZoom)), ratio=zoom/view.zoom;
  return clampView({zoom,x:(view.x+point.x)*ratio-point.x,y:(view.y+point.y)*ratio-point.y},scene,size);
}
export function fitView(scene,size,widthOnly=false) {
  return clampView({zoom:Math.min(size.width/scene.width,widthOnly?MAX_ZOOM:size.height/scene.height,1),x:0,y:0},scene,size);
}
export function cellIndex(scene,facet,row,col) {
  return scene.shape.length===1?col:(row*scene.cols+col)*scene.facets+facet;
}
export function hitBlockedCell(scene,view,point) {
  const x=(point.x+view.x)/view.zoom,y=(point.y+view.y)/view.zoom;
  const facet=Math.floor(y/scene.facetHeight),local=y-facet*scene.facetHeight-scene.header;
  const row=Math.floor(local/TILE.y),col=Math.floor(x/TILE.x);
  if(facet<0 || facet>=scene.facets || row<0 || row>=scene.rows || col<0 || col>=scene.cols || x%TILE.x>=TILE.width || local%TILE.y>=TILE.height) return null;
  return cellIndex(scene,facet,row,col);
}
export function visibleBlockedRange(scene,view,size) {
  const left=view.x/view.zoom,top=view.y/view.zoom,right=(view.x+size.width)/view.zoom,bottom=(view.y+size.height)/view.zoom;
  const ranges=[];
  const start=Math.max(0,Math.floor(top/scene.facetHeight)),end=Math.min(scene.facets-1,Math.floor(bottom/scene.facetHeight));
  for(let facet=start;facet<=end;facet++) {
    const origin=facet*scene.facetHeight+scene.header;
    ranges.push({facet,startRow:Math.max(0,Math.floor((top-origin)/TILE.y)),endRow:Math.min(scene.rows-1,Math.floor((bottom-origin)/TILE.y)),startCol:Math.max(0,Math.floor(left/TILE.x)),endCol:Math.min(scene.cols-1,Math.floor(right/TILE.x))});
  }
  return ranges;
}
export function facetLabel(scene,facet) {
  const values=[];
  for(let d=scene.shape.length-1;d>=2;d--) { values.unshift(`D${d} = ${facet%scene.shape[d]}`); facet=Math.floor(facet/scene.shape[d]); }
  return values.join(' · ');
}
