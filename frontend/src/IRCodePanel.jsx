import './ir-monaco';
import { useEffect, useRef } from 'react';
import Editor, { DiffEditor } from '@monaco-editor/react';

const options = { minimap: { enabled: false }, fontSize: 12, lineHeight: 23, fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', monospace", scrollBeyondLastLine: false, renderLineHighlight: 'line', padding: { top: 14, bottom: 14 }, automaticLayout: true, wordWrap: 'off', folding: true, glyphMargin: false, lineNumbersMinChars: 3, overviewRulerLanes: 1, renderOverviewRuler: true, fixedOverflowWidgets: true, stickyScroll: { enabled: false } };
// Remount the owner on document/stage changes so Monaco disposes the previous
// model instead of retaining every visited path in its global model registry.
export function IRCodePanel(props) { return <OwnedIRCodePanel key={`${props.path}:${props.original !== undefined}`} {...props}/>; }
function OwnedIRCodePanel({ content, language = 'triton-ir', readOnly = true, onChange, highlights = [], onLine, path, startLine = 1, reveal = true, original }) {
  const editor = useRef(null), diff = useRef(null), decorations = useRef(null), mouse = useRef(null), currentLine = useRef(onLine);
  currentLine.current = onLine;
  useEffect(() => () => {
    mouse.current?.dispose();
    if (diff.current) {
      // @monaco-editor/react otherwise disposes the models while the diff
      // widget still observes them. Detach first, then release owned models.
      const models = diff.current.getModel();
      diff.current.setModel(null);
      models?.original.dispose();
      models?.modified.dispose();
    }
  }, []);
  useEffect(() => {
    const instance = editor.current;
    if (!instance?.getModel()) return;
    const lines = highlights.filter(n => Number.isInteger(n) && n >= 1 && n <= instance.getModel().getLineCount());
    decorations.current?.set(lines.map(line => ({ range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 }, options: { isWholeLine: true, className: 'ir-linked-line', linesDecorationsClassName: 'ir-linked-gutter', overviewRuler: { color: '#149A8A', position: 7 } } })));
    if (reveal && lines.length) instance.revealLineInCenterIfOutsideViewport(lines[0]);
  }, [highlights.join(','), content, path, reveal]);
  const mount = instance => {
    editor.current = instance;
    decorations.current = instance.createDecorationsCollection();
    mouse.current?.dispose();
    mouse.current = instance.onMouseDown(e => { if (e.target.position) currentLine.current?.(e.target.position.lineNumber); });
    const lines = highlights.filter(n => Number.isInteger(n) && n >= 1 && n <= instance.getModel().getLineCount());
    decorations.current.set(lines.map(line => ({ range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 }, options: { isWholeLine: true, className: 'ir-linked-line', linesDecorationsClassName: 'ir-linked-gutter' } })));
  };
  if (original !== undefined) return <DiffEditor height="100%" original={original} modified={content} language={language} theme="triton-light" keepCurrentOriginalModel keepCurrentModifiedModel options={{ ...options, readOnly: true, renderSideBySide: false }} onMount={instance => { diff.current = instance; mount(instance.getModifiedEditor()); }}/ >;
  return <Editor height="100%" path={path} value={content} language={language} theme="triton-light" loading={<div className="ir-editor-loading">正在加载本地编辑器…</div>} onMount={mount} onChange={value => onChange?.(value || '')} options={{ ...options, readOnly, ariaLabel: readOnly ? 'IR 代码' : 'Triton kernel 源码', lineNumbers: n => String(n + startLine - 1) }}/>;
}
