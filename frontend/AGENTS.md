# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Selected direction

The user selected the first generated design: light surfaces, teal accents, fixed left navigation, a dense environment table, and a right-hand task drawer. Keep this visual hierarchy and clearly label browser demo data.

## Case execution preferences

Group collected configurations beneath their logical test function. Let users select individual parameterized nodeids. Expose pytest-xdist workers and per-worker logs; render additional run settings from server-owned extension schemas. Preserve the existing light/teal hierarchy.

## Profiling preferences

Keep profiling bound to one case configuration and one environment snapshot. Clearly distinguish mock board results from actual hardware measurements. Preserve timeline, kernel summaries and Chrome Trace interoperability; do not upload profiling data to external viewers automatically.

Profiling timelines should show multiple execution engines and tiled pipelines, including overlapping DMA/SDMA, matrix/vector work, synchronization, buffer slots and dependencies. Keep cumulative engine work separate from elapsed pipeline time.

Enable hover/focus-scoped keyboard zoom and horizontal pan in profiling timelines, with pointer-anchored modifier-wheel zoom, modifier-wheel pan, and visible shortcut hints. Preserve text input and normal page scrolling.

Keep the profiling timeline’s left engine/track name column fixed during horizontal panning and zooming; event bars, ticks and dependency lines scroll beneath an opaque label layer.

Batch run results should default to an overview with outcome counts, per-operator results, failure phases, slow configurations and rerun changes. Charts drill down into filtered cases. Count parameterized nodeids once, keep skips/incomplete separate, and use explicit operator metadata. Never invent timings or count untested parent configurations as recovered.

Provide a dedicated report preview grouped by file, class/function and parameter configuration. Render uppercase result labels such as PASS/FAIL/CRASH as coloured blocks inside table cells, include observed timing/worker/evidence, and keep missing data explicit. CRASH needs attributable process-exit evidence; never label all unexecuted configurations as crashes.

测试报告采用紧凑分组列表，默认折叠全部文件和用例；组名、配置数和结果计数尽量同行，减少留白。展开后保留参数与结果色块；切换运行重置展开状态。
