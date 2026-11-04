import { useMemo, useState } from 'react';
import { buildBlockedLayout, contiguousRuns } from './blocked-layout';
import { BlockedLayoutCanvas } from './BlockedLayoutCanvas';

const COLORS = ['#dcefe8','#e2e9fb','#f6e9ce','#eee2f5','#dceef5','#f5dfe6','#e7efd5','#e6e9ed'];
const DEFAULT = `#ttg.blocked<{
  sizePerThread = [1, 2],
  threadsPerWarp = [2, 16],
  warpsPerCTA = [2, 1],
  order = [1, 0],
  CGALayout = [[1, 0]]
}>`;
const runsText = xs => contiguousRuns(xs).map(([a,b]) => a === b ? `${a}` : `${a}–${b}`).join(', ');
const ownerText = o => `CTA ${o.block} · W${o.warp} · L${o.lane} · T${o.thread} · R${o.register}`;
export function BlockedLayoutTool() {
  const [shape,setShape] = useState('8, 32');
  const [source,setSource] = useState(DEFAULT);
  const [selection,setSelection] = useState(null);
  const computed = useMemo(() => {
    try {
      return {model:buildBlockedLayout(shape,source)};
    } catch (error) { return {error:error.message}; }
  },[shape,source]);
  const {model,error} = computed;
  const selected = selection?.model === model ? selection : null;
  const owner = selected?.cell?.owners[0];
  const thread = owner && model.threads.find(t => t.key === owner.key);
  const block = selected?.block !== undefined && model.blocks.find(b => b.id === selected.block);
  const highlighted = new Set((thread || block)?.indices || []);
  const choose = data => setSelection({model,...data});
  return <section className="tools-workspace blocked-tool" aria-label="Blocked Layout 工具">
    <header className="tools-heading"><h1>Blocked Layout</h1></header>
    <div className="blocked-layout">
      <div className="blocked-input">
        <label>Shape<input aria-label="Tensor shape" value={shape} maxLength={256} spellCheck={false} onChange={e=>setShape(e.target.value)}/></label>
        <label>Blocked layout<textarea aria-label="Blocked layout 输入" value={source} maxLength={16384} spellCheck={false} onChange={e=>setSource(e.target.value)}/></label>
      </div>
      <div className="blocked-output">
        <div className="blocked-output-heading"><span>数据分布</span><span>行优先索引 · T 线程 / R 槽位</span></div>
        {error ? <p className="cga-error" role="alert">{error}</p> : <>
          <div className="blocked-legend" aria-label="CTA 图例">{model.blocks.map(b=><span key={b.id} tabIndex={0} style={{'--block-color':COLORS[b.id%COLORS.length]}} onMouseEnter={()=>{if(!selected?.pinned)choose({block:b.id});}} onMouseLeave={()=>{if(!selected?.pinned)setSelection(null);}} onFocus={()=>choose({block:b.id})} onBlur={()=>setSelection(null)}>CTA {b.id}<small>{b.indices.length} 元素</small></span>)}</div>
          <BlockedLayoutCanvas model={model} highlighted={highlighted} selectedIndex={selected?.cell?.index} pinned={Boolean(selected?.pinned)}
            onHover={index=>{if(!selected?.pinned) setSelection(index===null?null:{model,cell:model.cells[index]});}}
            onPick={(index,toggle)=>setSelection(toggle&&selected?.pinned&&selected.cell?.index===index?null:{model,cell:model.cells[index],pinned:true})}
            onClear={()=>setSelection(null)}/>
          <div className="blocked-inspector" aria-live="polite">{owner ? <><strong>[{selected.cell.coord.join(', ')}] · {ownerText(owner)}</strong><span>该线程索引：{runsText(thread.indices)}{selected.cell.owners.length>1 && ` · 此元素有 ${selected.cell.owners.length} 份归属（高亮首份归属）`}</span>{selected.cell.owners.length>1 && <span>{selected.cell.owners.slice(0,8).map(ownerText).join('；')}{selected.cell.owners.length>8?`；另 ${selected.cell.owners.length-8} 份`: ''}</span>}</> : block ? <><strong>CTA {block.id} · {block.indices.length} 元素</strong><span>索引：{runsText(block.indices)}</span></> : <span>悬停元素查看坐标、线程与连续区间；点击固定高亮。</span>}</div>
        </>}
      </div>
    </div>
  </section>;
}
