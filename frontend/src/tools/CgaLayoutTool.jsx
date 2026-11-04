import { useMemo, useState } from 'react';
import { buildCgaLayout } from './cga-layout';
import '../tools.css';

const COLORS = ['#e1f0ed', '#e7ecfa', '#f7ecd9', '#eee6f6', '#e0edf4', '#f7e6eb', '#edf1df', '#e9edf0'];
const vector = xs => `[${xs.join(', ')}]`;
export function CgaLayoutTool() {
  const [source, setSource] = useState('[[0, 1], [1, 0]]');
  const computed = useMemo(() => {
    if (!source.trim()) return {};
    try {
      const layout = buildCgaLayout(source);
      const facets = new Map();
      layout.groups.forEach((tile, index) => {
        const key = tile.coord.slice(2).join(',');
        if (!facets.has(key)) facets.set(key, { key, fixed: tile.coord.slice(2), tiles: [] });
        facets.get(key).tiles.push({ ...tile, index });
      });
      return { layout, facets: [...facets.values()] };
    } catch (error) { return { error: error.message }; }
  }, [source]);
  const { layout, facets, error } = computed;
  return <section className="tools-workspace cga-simple" aria-label="CGA Layout 工具">
    <header className="tools-heading"><h1>CGA Layout</h1></header>
    <div className="cga-simple-layout">
      <label className="cga-simple-input">CGA layout<textarea aria-label="CGA layout 输入" value={source} onChange={e => setSource(e.target.value)} placeholder="[[0, 1], [1, 0]]" spellCheck={false} maxLength={16384}/></label>
      <div className="cga-simple-output"><span className="cga-simple-label">CTA tiles</span><div className="cga-simple-canvas" role="region" aria-label="CTA tile 排列" tabIndex={0}>
        {error ? <p className="cga-error" role="alert">{error}</p> : !layout ? <p className="cga-placeholder">输入布局后自动展示</p> : facets.map(facet => <div className="cga-facet" key={facet.key}>
          {facet.fixed.length > 0 && <p className="cga-facet-label">{facet.fixed.map((n, i) => `D${i + 2} = ${n}`).join(' · ')}</p>}
          <div className="cga-simple-grid" style={{ gridTemplateColumns: `repeat(${layout.rank === 1 ? layout.extents[0] : layout.extents[1]}, 136px)` }}>
            {facet.tiles.map(tile => <div className="cga-simple-tile" key={tile.key} style={{ backgroundColor: COLORS[tile.index % COLORS.length], gridRow: layout.rank === 1 ? 1 : tile.coord[0] + 1, gridColumn: layout.rank === 1 ? tile.coord[0] + 1 : tile.coord[1] + 1 }} title={`Tile ${vector(tile.coord)} · CTA ${tile.owners.join(', ')}`} aria-label={`Tile ${vector(tile.coord)} CTA ${tile.owners.join(', ')}`}>
              <span>{vector(tile.coord)}</span><strong>CTA {tile.owners.slice(0, 8).join(' · ')}{tile.owners.length > 8 ? ` · +${tile.owners.length - 8}` : ''}</strong>
            </div>)}
          </div>
        </div>)}
      </div></div>
    </div>
  </section>;
}
