# triton-dev

一个模块化的 SDK 环境、测试执行与证据驱动回归工具集。**v0.2 离线自动化原型，无需真实 Triton 即可运行离线测试。** 所有尚未接入真实环境的能力都会标记 `not_checked` 或返回 `UNSUPPORTED`，不会伪造成功。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
source .venv/bin/activate
triton-dev --help
triton-dev capabilities --json
triton-dev describe env.prepare --json
```

工具自身安装在独立 venv，避免被 SDK wheel 切换覆盖。运行时使用标准库和 packaging，支持 Python 3.10+、POSIX。SDK 的 cp310/Linux x86_64 wheel 仍要求相匹配的解释器和平台；本机 macOS 测试仅证明受控逻辑。

## 已实现的最小闭环

| 模块 | 当前能力 |
| --- | --- |
| env | 按名称扫描 SDK、日期选择、wheel 元数据/哈希、HTTP daily 下载、校验与安全解压、离线 venv 安装、Python 包覆盖、变量导出、子进程和终端使用 |
| build | 六个源码目标的发现与 plan；实际编译明确不支持 |
| cases / pytest_plugin | 独立进程中的真实 pytest collection，包含参数化 nodeid 和 markers |
| run / execution | 子进程隔离、流式有界日志；runs 显式持久化、pytest 阶段结果、失败项复测 |
| diagnose | good/bad 对照、结构化故障判据、预算内穷举历史搜索；不自动推断组件/commit 归属 |
| agent | 离线 ScriptedModel、只读协议与登记实验工作流、预算、checkpoint 恢复及证据校验；无实时模型调用 |
| report / doctor | 已有证据摘要、脱敏证据包导出和完整性校验、只读预检 |
| serve | loopback 能力查询、可选鉴权任务队列、幂等提交、取消、恢复和 SSE；可选同源网页前端 |

状态总览见 [STATUS.md](STATUS.md)，每个模块维护自己的 `TODO.md`，明确已完成、待办和验收条件。

## 新增离线自动化

已加入命名版本组合、wheel 预检、持久运行与复测、结构化判据、历史搜索、证据包、脚本 agent 工作流及任务 API。命令、配置和验证边界见 [离线自动化操作手册](docs/OFFLINE.md)。可运行 `python examples/offline_demo.py --workdir /new/demo-directory` 体验完整合成 SDK 闭环。

## 网页前端

浅色/青绿工作台位于 frontend/，支持组合创建、版本比较、用例运行和诊断的完整演示。真实 API 已接入登记任务和 pytest 项目的收集、隔离运行、阶段结果与失败项复测；环境组合与诊断仍明确标为演示。开发预览及 `serve --ui` 使用方式见 [前端说明](frontend/README.md)。

## 使用

默认 SDK 根目录 `/login_home`、下载 URL 和命名规则集中在 `triton_dev/env/settings.py`。无需管理用户 YAML。`--sdk-root`、`--cache-root` 是测试/高级覆盖参数，不会修改默认配置。

```bash
triton-dev env sdk list
triton-dev env sdk inspect --sdk TX82_SDK_Daily_2026-10-22-02-52
triton-dev env download
triton-dev env download 20261022

# 显式选择解释器，预览后离线安装完整依赖组合
triton-dev env plan --sdk latest
triton-dev env prepare --sdk latest --python /path/to/python3.10
triton-dev env verify --sdk latest --python /path/to/python3.10
triton-dev env exec --sdk latest --python /path/to/python3.10 -- python -m pytest tests/smoke

# 不改变当前终端，导出相关变量（指定 SDK 必须已 prepare）
triton-dev env export --current --format sh
triton-dev env export --sdk latest --format sh
triton-dev env export --current --format json --output environment.json
```

`--python` 支持可执行路径或 PATH 中的名称，实际由该解释器创建隔离 venv，并在安装前核对 Python 版本和平台。创建失败返回 `VENV_CREATION_FAILED`，身份不符返回 `PYTHON_IDENTITY_MISMATCH`，均不发布 ready 状态。准备协议 v3 不复用旧版环境缓存；已有目录不会被自动覆盖或删除。此校验不等于 wheel ABI 或原生运行验证。

指定 SDK 导出不会默认安装，只有显式 `--prepare` 才准备。`--current` 只读当前进程继承的 export 变量，不读取父 shell 局部变量/函数。输出含 `variables` 和 `unset`；显式文件权限设为 0600。JSON 模式输出版本化 envelope，进度和菜单不混入 stdout。

终端集成（bash/zsh）：

```bash
eval "$(triton-dev shell-init bash)"
triton-dev env use --sdk latest
triton-dev env update
triton-dev env deactivate
```

每个终端独立绑定环境；切换不会修改其他终端或已经运行的进程。`update` 获取远端最新整套 SDK，失败不应用变量；不会覆盖活动 venv。未集成时使用 `env shell` 子终端，直接 `env use` 会提示需要集成。

人工候选选择示例：`triton-dev env plan -i`；自动化使用完整参数和 `--non-interactive`。目前交互为实际候选的编号选择，搜索式 TUI 是 TODO；Python wheel 来源混合及命名组合保存已支持。显式的 `--cmodel-sdk` 当前返回 `UNSUPPORTED`，因为共享 lib 的组件归属未确认。

## 无 Triton 环境的演示与测试

```bash
python -m pytest -q
ruff check .
python -m build
```

测试在临时目录生成明确标记的合成 wheel/SDK，通过本地 HTTP 下载、真实 venv/pip、真实 pytest collection、bash/zsh 和并行子进程验证。不是在测试真实 Triton 或 cmodel。

`--native-only` 显式只设置原生路径，不安装/验证 SDK Python 包或实际原生库，适合受控脚本及测试适配，不可将其结果报告为完整环境验证。

```bash
triton-dev diagnose compare --good <SDK-A> --bad <SDK-B> \
  --native-only --match TARGET_FAILURE --repeat 3 -- python ./reproduce.py

triton-dev cases list ./tests --json
triton-dev build list --workspace /path/to/source-workspace
triton-dev build triton --workspace /path/to/source-workspace --plan
triton-dev doctor --json
```

`diagnose compare` 只定位 SDK 更新关联，不自动断言组件/仓库/commit 根因。错误签名不一致、基线失败、未稳定复现分别报告。

## 下载限制与真实接入

下载器实现标准 HTML 目录列表适配器，可用本地 HTTP 测试。内部 JFrog 列表 API/认证尚未在真实服务验证。可设置 `TRITON_DEV_TOKEN` 传递 bearer token；工具不打印它。真实 SDK 若包含软/硬链接，当前安全策略拒绝解压，须确认链接规则后接入，不能关掉校验绕过。

原生加载、ABI、组件混用、真实源码构建和模型 provider 均有明确 TODO。详情见 [真实环境接入](docs/INTEGRATION.md)。

## 文档

- [设计与模块契约](docs/DESIGN.md)
- [CLI 与 AI 接口](docs/INTERFACES.md)
- [开发与 CI 规则](CONTRIBUTING.md)
- [AI/代码协作规则](AGENTS.md)
- [当前进度](STATUS.md)
- [pytest 服务、隔离与复测](docs/PYTEST_SERVER.md)
- [单服务器多人平台目标架构](docs/MULTI_USER_SERVER.md)
- [SDK 回归定位 Agent 设计](docs/REGRESSION_AGENT.md)

原有 env exec 默认不生成报告；新增 runs、agent workflow 和 Server tasks 显式写入本地运行记录。可分享报告由显式导出命令或 `--output` 产生，准备状态与锁集中在工具缓存。没有必需的第三方服务或数据库。

## 参数配置与 xdist 增量（未提交）

- 已实现：逻辑用例分组与参数实例单选/多选；单次运行 xdist workers、每 worker 日志/进度/PID/独立缓存；失败复测保留 workers 与扩展选项。
- 扩展接口：服务登记 schema/default/version/固定编译函数，项目 allowlist；内置失败阈值、慢阶段统计和输出捕获。HTTP 不接受自由命令。
- xdist 同次运行共享源码工作目录，设备尚无租约；默认逐 case 模式保留。远程多用户身份及任意 fixture 参数覆盖仍待实现。
- 验证：Python 105 passed、ruff通过；前端模型5项和静态打包4项通过。详细使用及边界见 docs/PYTEST_SERVER.md。

## Profiling demo

网页新增Profiling入口，模拟单case与环境下的板卡事件/计数器，并生成可交互性能报告。支持原始JSON与Chrome Trace导出，供Perfetto查看。此demo不执行真实板卡测试；使用方法、口径和接入边界见[Profiling说明](docs/PROFILING.md)。

网页运行详情新增[批次统计总览](docs/RUN_STATISTICS.md)，按配置去重展示结果/算子/阶段分布、慢配置和复测变化，支持图表联动筛选；operator元数据可显式标注。

[测试报告预览](docs/TEST_REPORT.md)按文件、逻辑用例和配置展示结果色块、执行时间与证据，提供独立页面和离线HTML/JSON导出。

回归定位工具首版已支持mock SDK/模型 + 真实CPU pytest的CLI与网页闭环，见[使用说明](docs/REGRESSION_USAGE.md)。真实SDK/板卡/模型API尚未接通。

## 多用户数据库服务

使用 `pip install -e '.[server]'` 与 `serve --multi-user` 启用姓名登录、个人空间、个人模型配置和数据库数据中心。正式共享模式使用 PostgreSQL；操作、管理 CLI 和当前边界见 [PLATFORM_USAGE.md](docs/PLATFORM_USAGE.md)。真实模型 API、SDK Builder 和设备隔离仍待接入。

界面布局、模块设计原则与公共颜色 / 间距规范见 [UI_DESIGN.md](docs/UI_DESIGN.md)，浏览器验收与预览见 [UI_REFINEMENT_QA.md](docs/UI_REFINEMENT_QA.md)。
