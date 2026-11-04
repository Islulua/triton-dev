import { IconArrowRight, IconGridDots, IconTools } from '@tabler/icons-react';
import { CgaLayoutTool } from './tools/CgaLayoutTool';
import './tools.css';
import { BlockedLayoutTool } from './tools/BlockedLayoutTool';

// One registration and one component per independent helper page.
const HELPERS = [{ route: 'tools-cga', title: 'CGA Layout', category: 'LAYOUT', description: '把布局参数转换为 CTA tile 排列，查看切分、编号与复制关系。', scope: '1–4 维 · Linear / Legacy', Icon: IconGridDots, Component: CgaLayoutTool }, { route: 'tools-blocked', title: 'Blocked Layout', category: 'LAYOUT', description: '根据 shape 和布局查看 CTA、线程的数据分布与连续性。', scope: '1–4 维 · Blocked', Icon: IconGridDots, Component: BlockedLayoutTool }];
export function ToolsWorkspace({ page, onNavigate }) {
  const helper = HELPERS.find(h => h.route === page);
  if (helper) { const Component = helper.Component; return <Component onNavigate={onNavigate}/>; }
  return <section className="tools-workspace"><header className="tools-heading"><div><span className="tools-eyebrow">DEVELOPER HELPERS</span><h1>Tools</h1><p>独立的小工具，随手打开即可使用。</p></div><span className="tools-local"><IconTools size={15}/>本地计算</span></header><div className="tools-catalog">{HELPERS.map(({ route, title, category, description, scope, Icon }) => <button key={route} className="tools-helper-card" onClick={() => onNavigate(route)}><span className="tools-helper-icon"><Icon size={25}/></span><div><span className="tools-card-tag">{category}</span><h2>{title}</h2><p>{description}</p><div className="tools-card-foot"><span>{scope}</span><IconArrowRight size={18}/></div></div></button>)}</div></section>;
}
