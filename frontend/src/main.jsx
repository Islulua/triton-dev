import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";
import "./refine.css";
const IRDetachedWorkspace = React.lazy(() => import('./KernelWorkspace.jsx').then(module => ({ default: module.IRDetachedWorkspace })));

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).has('ir_window') ? <React.Suspense fallback={<p>正在加载 IR 窗口…</p>}><IRDetachedWorkspace /></React.Suspense> : <App />}
  </React.StrictMode>,
);
