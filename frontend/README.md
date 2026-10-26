# triton-dev 网页工作台

沿用选定的浅色 / 青绿色设计：固定左导航、任务内容区、按需打开的右侧抽屉。四个主分区为工作台、环境与制品、用例与运行、诊断与证据；连接设置独立放在底部。

## 本地开发

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

默认是浏览器演示模式。组合创建/导入检查、用例运行、数值失败及版本对照均为明确标记的前端演示，不安装 SDK 或执行 kernel。演示组合/记录保存在本浏览器；未完成的演示操作在刷新后标为未验证/已中断。

## 对接现有本地任务 API

```bash
npm run build
# 在项目根目录，预先设置 TRITON_DEV_SERVER_TOKEN（至少16字符）
triton-dev serve --jobs /path/to/jobs.json --ui frontend/dist/client --port 8765
```

打开同一服务的根路径，在设置页输入访问令牌。令牌只在页面内存中使用，不写入 URL、localStorage 或源码；刷新后需重新连接。任务 API 的身份校验保留，同源 Origin 可访问，跨源仍拒绝。

开发服务把 `/api` 代理到 `http://127.0.0.1:8765`；可通过启动 Vite 前设置 `TRITON_DEV_API_TARGET` 改为其他本地 HTTP 地址，不支持远程地址。代理只改写匹配当前开发源的 Origin，不放行跨源浏览器请求。

真实接入范围：登记任务与 pytest 项目；项目可真实收集、选择参数实例、隔离运行和复测，普通任务可查询/提交/取消。网页不能提交自由 argv 或任意 pytest 选项。请求响应未知时重试沿用同一幂等键。

环境组合、任意参数覆盖、版本诊断尚未接入真实 HTTP 服务。离线模式的用例库仍为演示，已连接的 pytest 项目工作区使用真实数据。切到本地任务模式不会把这些演示流程变成实际操作。真实任务结果不补造 kernel 阶段或数值观察。

网页导出 JSON 是当前记录快照，不是 CLI 的完整脱敏 ZIP。Server tasks 和 CLI runs 使用独立状态目录；CLI 导出模板中的 `<CLI_RUN_ID>` 必须替换为实际 CLI 运行 ID。

## 主要交互

- 组合：搜索/空结果、SDK 切换、冻结来源、新建/保存草稿、名称校验、演示准备、查看快照、对比来源。
- 用例：搜索、最近失败过滤、批量选择、fixture 详情、选择组合与 M/N 参数、演示运行。
- 运行：排队/运行/终止、取消、原记录保留、失败项复测、结果/日志/环境快照/证据 tabs。
- 诊断：显式基线/候选、相同组合拒绝、固定演示观察、证据摘要、脚本助手说明。
- 小屏：折叠导航、全宽侧栏、独立表格横向滚动、模态侧栏键盘焦点约束、Escape 关闭。

```bash
npm test
npm run build
npm run test:sites
```

参考及浏览器验收图放在 `design/`，视觉对照报告在 `design-qa.md`。没有部署到外部站点。

Python wheel 不包含网页资源；请从仓库或 sdist 的 frontend/ 构建网页，再用 --ui 指定构建目录。依赖安装需要 npm 包源或事先准备的离线 npm 缓存。

## 真实 pytest 项目

连接服务后，“用例与运行 → pytest 项目”支持真实收集、参数实例筛选、逐 case/session 隔离、阶段结果/日志/context/附件及失败项/全部复测。“命令任务”保留旧任务入口。测试使用固定登记的解释器和收集源码快照；要验证源代码或依赖更新请重新收集。完整配置和边界见 ../docs/PYTEST_SERVER.md。

## 参数配置与 xdist 增量（未提交）

- 已实现：逻辑用例分组与参数实例单选/多选；单次运行 xdist workers、每 worker 日志/进度/PID/独立缓存；失败复测保留 workers 与扩展选项。
- 扩展接口：服务登记 schema/default/version/固定编译函数，项目 allowlist；内置失败阈值、慢阶段统计和输出捕获。HTTP 不接受自由命令。
- xdist 同次运行共享源码工作目录，设备尚无租约；默认逐 case 模式保留。远程多用户身份及任意 fixture 参数覆盖仍待实现。
- 验证：Python 105 passed、ruff通过；前端模型5项和静态打包4项通过。详细使用及边界见 docs/PYTEST_SERVER.md。

Profiling导航提供内置mock报告预览；连接本地API后可选择模拟case/环境并生成、保存和切换报告。支持时间线采样/缩放/事件详情及JSON/Chrome Trace导出，真实板卡尚未接入。详见../docs/PROFILING.md。

运行详情默认进入“运行总览”，支持批次结果/算子分布/失败阶段/最慢配置及复测变化，图表可筛选到配置详情。真实pytest与浏览器演示来源分别标注；演示缺失计时不补造。详见../docs/RUN_STATISTICS.md。

测试报告可从左侧导航或运行详情“报告预览”进入，按文件/用例/配置展示带PASS、FAIL、CRASH等标签的色块，支持时间、worker、失败详情及完整HTML/JSON导出。详见../docs/TEST_REPORT.md。
