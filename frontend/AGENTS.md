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

回归定位提供独立网页入口，保持浅色青绿和紧凑表格；可查看版本搜索、组件干预、模型决策及报告，始终显著标记mock范围。

Agent采用左侧可展开任务分组，回归定位作为子模块；其他子模块在接通前明确标记待接入。回归页面遵循2026-10-27选定预览图：结论优先、五步进度、版本搜索、组件双向对照，默认折叠新建配置与原始日志，保留复制摘要/完整复现命令和报告/证据包下载。

2026-10-27 未连接回归演示：默认展示浏览器预设完整样例，可自动播放/暂停、上一步/下一步及跳转阶段；无需token或服务API。演示数据/日志/报告明确标注未执行pytest、未调用模型，禁用实际复现命令，连接服务才运行真实CPU实验。

## 简约 UI 规范（2026-10-27）

各模块遵循 docs/UI_DESIGN.md，公共 token 与组件规则位于 src/refine.css。优先显示结果与主要操作；删除重复说明、全局页脚和重复用户信息。原始日志、快照、完整ID、统计定义默认折叠，必要来源/错误/未知状态不能省略。表格紧凑、对齐统一，报告结果维持带文字色块。Profiling 默认报告优先，新建采样收起；未发现回归时不展示未执行的搜索、空组件矩阵或无效复现操作。

Daily 日历采用有间距的独立圆角日期卡片，柔和红绿底色；减少重复状态文字和长篇说明，优先呈现日期、PASS 数量、耗时与少量异常标记。模拟来源保留，完整质量口径和复测规则按需查看。
