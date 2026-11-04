import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { blockedScene, clampView, zoomAt, fitView, visibleBlockedRange, hitBlockedCell, cellIndex, facetLabel, TILE, MIN_ZOOM, MAX_ZOOM } from './blocked-view';
const COLORS=['#dcefe8','#e2e9fb','#f6e9ce','#eee2f5','#dceef5','#f5dfe6','#e7efd5','#e6e9ed'];
const percent = zoom => `${Number((zoom*100).toFixed(zoom<.0001?3:2))}%`;
export function BlockedLayoutCanvas({model,highlighted,selectedIndex,pinned,onHover,onPick,onClear}) {
  const scene=useMemo(()=>blockedScene(model.shape),[model]);
  const host=useRef(null),canvas=useRef(null),drag=useRef(null),hover=useRef(null);
  const [size,setSize]=useState({width:600,height:440});
  const [view,setView]=useState({zoom:1,x:0,y:0});
  const [mode,setMode]=useState('cta');
  const [dragging,setDragging]=useState(false);
  const live=useRef();
  live.current={view,size,scene,onHover,onPick,onClear,pinned};
  useLayoutEffect(()=>{
    const el=host.current;
    const observer=new ResizeObserver(()=>{
      const next={width:el.clientWidth,height:el.clientHeight};
      setSize(next); setView(v=>clampView(v,scene,next));
    });
    observer.observe(el); return ()=>observer.disconnect();
  },[scene]);
  useLayoutEffect(()=>{
    const size={width:host.current.clientWidth,height:host.current.clientHeight};
    setSize(size); setView(model.cells.length>256?fitView(scene,size):{zoom:1,x:0,y:0}); hover.current=null;
  },[model,scene]);
  useEffect(()=>{
    const el=canvas.current;
    const wheel=e=>{
      if(!(e.ctrlKey||e.metaKey)) return; // Preserve ordinary page scrolling.
      e.preventDefault();
      if(!live.current.pinned) {hover.current=null;live.current.onHover(null);}
      const {scene,size}=live.current,rect=el.getBoundingClientRect();
      const point={x:e.clientX-rect.left,y:e.clientY-rect.top};
      const factor=Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.006);
      setView(v=>zoomAt(v,v.zoom*factor,point,scene,size));
    };
    el.addEventListener('wheel',wheel,{passive:false}); return ()=>el.removeEventListener('wheel',wheel);
  },[]);
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>{
      const el=canvas.current,ctx=el.getContext('2d'),ratio=Math.min(window.devicePixelRatio||1,2);
      el.width=Math.round(size.width*ratio); el.height=Math.round(size.height*ratio);
      ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,size.width,size.height);
      ctx.fillStyle='#fbfcfd';ctx.fillRect(0,0,size.width,size.height);
      const z=view.zoom,gap=z<.12?0:Math.min(4*z,4),w=TILE.x*z-gap,h=TILE.y*z-gap;
      for(const range of visibleBlockedRange(scene,view,size)) {
        const {facet,startRow,endRow,startCol,endCol}=range;
        const origin=facet*scene.facetHeight+scene.header;
        if(scene.header && z>=.25) {
          ctx.globalAlpha=1;ctx.fillStyle='#627886';ctx.font='11px system-ui';ctx.textAlign='left';ctx.textBaseline='alphabetic';
          ctx.fillText(facetLabel(scene,facet),4,(origin-8)*z-view.y);
        }
        for(let row=startRow;row<=endRow;row++) for(let col=startCol;col<=endCol;col++) {
          const index=cellIndex(scene,facet,row,col),cell=model.cells[index],o=cell.owners[0];
          const x=col*TILE.x*z-view.x,y=(origin+row*TILE.y)*z-view.y;
          const active=highlighted.has(index);
          ctx.globalAlpha=highlighted.size && !active ? .24 : 1;
          if(mode==='cta') ctx.fillStyle=COLORS[o.block%COLORS.length];
          else if(mode==='warp') ctx.fillStyle=`hsl(${(o.block*83+o.warp*39)%360} 48% 78%)`;
          else ctx.fillStyle=`hsl(${(o.block*83+o.thread*137.508)%360} 52% 76%)`;
          ctx.fillRect(x,y,w,h);
          if(active) {ctx.strokeStyle='#087f83';ctx.lineWidth=1.5;ctx.strokeRect(x+.75,y+.75,Math.max(0,w-1.5),Math.max(0,h-1.5));}
          if(w>=32 && h>=22) {
            ctx.fillStyle='#233d4a';ctx.textAlign='center';ctx.textBaseline='middle';
            ctx.font=`600 ${Math.min(18,Math.max(9,12*z))}px monospace`;
            ctx.fillText(String(index),x+w/2,y+h*(w>=54?.35:.5),Math.max(1,w-3));
            if(w>=54 && h>=39) { ctx.font=`${Math.min(13,9*z)}px monospace`;ctx.fillText(`T${o.thread}:R${o.register}`,x+w/2,y+h*.72,w-4); }
            if(cell.owners.length>1 && w>=54) {ctx.textAlign='right';ctx.font='9px system-ui';ctx.fillText(`×${cell.owners.length}`,x+w-2,y+7);}
          }
        }
      }
      ctx.globalAlpha=1;
    });
    return ()=>cancelAnimationFrame(frame);
  },[model,scene,view,size,highlighted,mode]);
  const zoom = value=>setView(v=>zoomAt(v,value,{x:size.width/2,y:size.height/2},scene,size));
  const point=e=>{const rect=canvas.current.getBoundingClientRect();return {x:e.clientX-rect.left,y:e.clientY-rect.top};};
  const move=e=>{
    const p=point(e),d=drag.current;
    if(d) {
      const dx=e.clientX-d.x,dy=e.clientY-d.y;
      if(Math.abs(dx)+Math.abs(dy)>3) d.moved=true;
      if(d.moved) {setDragging(true);setView(clampView({...d.view,x:d.view.x-dx,y:d.view.y-dy},scene,size));}
      return;
    }
    const index=hitBlockedCell(scene,view,p);
    if(index!==hover.current) {hover.current=index;onHover(index);}
  };
  const keyDown=e=>{
    if(['+','=','-','0','Escape','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
      e.preventDefault();
      if(e.key==='Escape') {onClear();return;}
      if(e.key==='0') {zoom(1);return;}
      if(['+','=','-'].includes(e.key)) {zoom(view.zoom*(e.key==='-'?1/1.25:1.25));return;}
      const stride=scene.cols*scene.facets;
      const delta={ArrowLeft:-scene.facets,ArrowRight:scene.facets,ArrowUp:-stride,ArrowDown:stride}[e.key];
      const index=Math.max(0,Math.min(model.cells.length-1,(selectedIndex??0)+delta));
      onPick(index,false);
      const cell=model.cells[index],facet=index%scene.facets;
      const col=model.shape.length===1?index:cell.coord[1],row=model.shape.length===1?0:cell.coord[0];
      const x=col*TILE.x*view.zoom,y=(facet*scene.facetHeight+scene.header+row*TILE.y)*view.zoom;
      setView(v=>clampView({...v,x:x<v.x?x:x+TILE.x*v.zoom>v.x+size.width?x+TILE.x*v.zoom-size.width:v.x,y:y<v.y?y:y+TILE.y*v.zoom>v.y+size.height?y+TILE.y*v.zoom-size.height:v.y},scene,size));
    }
  };
  return <>
    <div className="blocked-canvas-toolbar"><label>着色<select aria-label="分布着色" value={mode} onChange={e=>setMode(e.target.value)}><option value="cta">CTA</option><option value="warp">Warp</option><option value="thread">Thread</option></select></label><div className="blocked-zoom" role="group" aria-label="分布图缩放">
      <button type="button" aria-label="缩小分布图" disabled={view.zoom<=MIN_ZOOM} onClick={()=>zoom(view.zoom/1.25)}>−</button>
      <button type="button" className="blocked-zoom-value" title="恢复 100%" aria-label={`当前缩放 ${percent(view.zoom)}，点击恢复100%`} onClick={()=>zoom(1)}>{percent(view.zoom)}</button>
      <button type="button" aria-label="放大分布图" disabled={view.zoom>=MAX_ZOOM} onClick={()=>zoom(view.zoom*1.25)}>+</button>
      <button type="button" className="blocked-zoom-fit" onClick={()=>setView(fitView(scene,size))}>总览</button>
      <button type="button" className="blocked-zoom-fit" onClick={()=>setView(fitView(scene,size,true))}>适应宽度</button>
    </div></div>
    <div className="blocked-canvas-host" ref={host}><canvas ref={canvas} className={dragging?'is-dragging':''} tabIndex={0} role="img" aria-label={`元素分布图，shape ${model.shape.join('×')}，${model.cells.length} 元素。方向键查看元素，加减号缩放，0复位，Escape解除固定。`} onKeyDown={keyDown}
      onPointerDown={e=>{if(e.button!==0)return;canvas.current.focus();canvas.current.setPointerCapture(e.pointerId);drag.current={x:e.clientX,y:e.clientY,view,moved:false};}}
      onPointerMove={move} onPointerUp={e=>{const d=drag.current;drag.current=null;setDragging(false);if(d&&!d.moved){const index=hitBlockedCell(scene,view,point(e));if(index!==null)onPick(index,true);} if(canvas.current.hasPointerCapture(e.pointerId))canvas.current.releasePointerCapture(e.pointerId);}}
      onPointerCancel={()=>{drag.current=null;setDragging(false);}} onPointerLeave={()=>{if(!drag.current){hover.current=null;onHover(null);}}}/></div>
    <div className="blocked-canvas-hint"><span>Ctrl / ⌘ + 滚轮缩放 · 拖动平移 · 点击固定线程</span>{pinned && <button onClick={onClear}>解除固定</button>}</div>
  </>;
}
