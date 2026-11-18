# triton-dev Harness 插件

设计、能力矩阵与内网迁移：[HARNESS_ARCHITECTURE.md](../docs/HARNESS_ARCHITECTURE.md)。

## 安装与启动

可运行 `bash harness/scripts/setup.sh` 完成下列安装，随后 `(cd harness && npm start)` 启动。安装与数据保存在仓库外 `/workspace/triton-harness`，可用 `TRITON_HARNESS_ROOT` 覆盖。

要求 Node >=24.9、Python >=3.10、bash/zsh。已验证官方 npm `@deepseek-ai/dsh@0.2.2-rc.1` 的插件加载、页面与代理；源码接口审阅基线为 `ca33fd6843b205e279c7ccb6cb73a472c78f5760`；上游 0.2.2-rc.4 为开发预览，npm 拆分包不能按同版本推测。

在 triton-dev 根目录安装并构建：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
(cd frontend && npm ci && TRITON_DEV_UI_BASE=/triton/ npm run build)
(cd harness && npm ci && npm run build && npm test)
```

安装已验证的官方发行版（与工具插件独立，不修改上游）：

```bash
npm install --prefix /workspace/triton-harness/runtime @deepseek-ai/dsh@0.2.2-rc.1
```

也可以把上游 Harness 克隆到当前仓库之外，固定上述源码 commit，按其 README 构建；源码全量安装需要 `cdn.sheetjs.com`，当前环境该域返回 403，所以此路线未完成。官方 npm 发行版已能独立运行，不依赖这次源码构建。

后端 demo 使用独立数据根目录，首次生成示例 registry（包含故意失败的 CPU 用例）：

```bash
.venv/bin/python examples/pytest_server_demo.py --workdir /workspace/triton-harness/demo
TRITON_DEV_DATABASE_URL=sqlite:////workspace/triton-harness/backend/platform.sqlite \
.venv/bin/triton-dev serve --multi-user \
  --jobs /workspace/triton-harness/demo/jobs.json \
  --cache-root /workspace/triton-harness/backend --port 8765
```

上面的显式 SQLite URL 用于本机开发；多用户内网版按设计文档替换身份与 PostgreSQL。后端启动与 Harness 启动是两个进程，不能依赖快照保存进程。

生成只增加插件的 overlay（把路径改为你的 checkout）：

```yaml
- insert:
    - id: triton-dev-workbench
      name: triton-dev-harness
      config:
        repository: /workspace/triton-dev
        python: /workspace/triton-dev/.venv/bin/python
        backend: http://127.0.0.1:8765
        sdkRoot: /workspace/triton-harness/sdks
        cacheRoot: /workspace/triton-harness/cache
        uiRoot: /workspace/triton-dev/frontend/dist/client
        enableWrites: true
```

先使用原生插件管理安装本地包：

```bash
export DSH_HOME=/workspace/triton-harness/home
/workspace/triton-harness/runtime/node_modules/.bin/dsh plugin --profile web add /workspace/triton-dev/harness
/workspace/triton-harness/runtime/node_modules/.bin/dsh web --patch /workspace/triton-harness/triton.patch.yml --no-open
```

`dsh plugin` 需要 pnpm 可用；本次使用 11.28.5。上面的 YAML 保存为 `/workspace/triton-harness/triton.patch.yml`。本地包安装与加载 overlay 缺一不可，不能把目录路径当 ESM 模块导入。

使用上游原有 web profile 加载 `--patch /absolute/path/triton.patch.yml`；不要替换默认 profile 或删除已有插件。树外插件持久安装可使用该版本上游的 `dsh plugin` 管理命令。AI 模型和凭据仍通过 Harness 原有设置配置，triton 插件不覆盖。

打开一个对话，右侧面板的新建入口选择 triton-dev。调用 `triton_open_page` 可切换所有原页面；工具结果卡片提供“在工作台查看”。无真实模型凭据时仍可使用工作台，不能声称完成了真实 AI 工作流。

## 示例 AI 指令

- “列出登记 pytest 项目，收集 demo 项目，只运行 size=64 的配置，完成后展示详情。”
- “读取 Profiling catalog，用它支持的 mock case 和 environment 创建报告，展示 timeline，明确标注不是板卡实测。”
- “计算 `[[0,1],[1,0]]` 的 CGA layout 并打开布局页面。”
- “查询 Daily 批次，读取失败 case 的日志，生成带 task id 和证据引用的摘要。”

HTTP 工具名由 method + path 生成，例如 `triton_api_post_tasks`、`triton_api_get_tasks_task_id`、`triton_api_post_pytest_runs`、`triton_api_post_profiling_reports`。参数为 `{params,query,body}`，路径参数放 params，查询值为字符串，body 使用原 API JSON。

收集的 body 为 `{job_id,idempotency_key}`；运行用 `{collection_id,nodeids,isolation,idempotency_key,workers,extensions}`；Profiling 用 `{case_id,environment_id,adapter:"mock",warmup,repeats,seed,idempotency_key}`，case/environment 应从 catalog 获取。异步任务必须查询终态，不要把提交成功说成测试通过。具体字段与语义沿用原 docs。

## 验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m build
(cd frontend && npm test && npm run test:sites)
(cd harness && npm test && npm run build)
```

Node 适配器测试会注册全工具目录，保留现有工具，运行真实 CLI worker、共享布局计算，并用本地 HTTP 验证 Cookie/CSRF 会话隔离。它不替代上游真实 Cordis 插件加载和浏览器/模型验收。

实际服务闭环验收：后端启动后执行 `TRITON_TEST_BACKEND=http://127.0.0.1:8766 node harness/scripts/smoke.mjs`。该脚本通过工具入口执行真实 CPU 收集与单配置运行，再创建 mock Profiling 并读取报告；没有模型请求。

完成依赖安装和插件安装后，可以在 `harness/` 运行 `npm start` 同时启动后端和 Harness，退出时清理本脚本启动的进程。支持 `TRITON_HARNESS_ROOT`、`TRITON_DSH_BIN`、`TRITON_BACKEND_PORT` 和 `TRITON_HARNESS_PORT`；首次使用会生成独立示例 registry。端口已占用时停止，避免连接到其他实例。
