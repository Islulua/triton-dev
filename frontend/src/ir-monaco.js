import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution';
import 'monaco-editor/esm/vs/editor/contrib/find/browser/findController';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });
monaco.languages.register({ id: 'triton-ir' });
monaco.languages.setMonarchTokensProvider('triton-ir', { tokenizer: { root: [
  [/\/\/.*$|;.*$/, 'comment'], [/"[^"\n]*"/, 'string'], [/%[\w.$-]+/, 'variable'],
  [/@[\w.$-]+/, 'type.identifier'], [/\b(?:module|func|define|return|ret|call|loc|to|step|public)\b/, 'keyword'],
  [/\b(?:tt|arith|scf|memref|core|tx81|llvm)\.[\w_]+/, 'keyword'],
  [/\b(?:tensor|vector|memref|ptr|f32|f16|i32|i64|index|void)\b/, 'type'], [/\b\d+\b/, 'number'],
] } });
monaco.editor.defineTheme('triton-light', { base: 'vs', inherit: true, rules: [
  { token: 'keyword', foreground: '087F82' }, { token: 'variable', foreground: '77518B' },
  { token: 'comment', foreground: '88959F' }, { token: 'number', foreground: '9A641D' },
], colors: { 'editor.background': '#FFFFFF', 'editorLineNumber.foreground': '#A1ADB6', 'editor.lineHighlightBackground': '#F5F8F9', 'editor.selectionBackground': '#D6EEEB', 'editorGutter.background': '#FFFFFF', 'editorCursor.foreground': '#087F82' } });
export { monaco };
