# 实现进度

v0.2：离线自动化原型。未接入真实 Triton、cmodel、设备、内部 JFrog 或 live AI。默认离线测试通过不代表真实环境通过。

| 模块 | 当前进度 |
| --- | --- |
| [env](triton_dev/env/TODO.md) | 命名组合、wheel 预检、离线准备/切换；原生边界待接入 |
| [build](triton_dev/build/TODO.md) | 接口与目标发现已实现，真实编译未实现 |
| [cases](triton_dev/cases/TODO.md) | 真实 collection、详情和 case ID lint |
| [execution](triton_dev/execution/TODO.md) | 有界流式输出、持久运行、pytest 阶段和失败项复测 |
| [diagnosis](triton_dev/diagnosis/TODO.md) | 结构化判据、SDK 对照和预算内穷举历史搜索 |
| [agent](triton_dev/agent/TODO.md) | 离线协议与登记实验工作流、checkpoint/预算；无实时 AI |
| [reporting](triton_dev/reporting/TODO.md) | 对照摘要、脱敏证据包导出/完整性校验 |
| [doctor](triton_dev/doctor/TODO.md) | 基础只读预检已实现 |
| [pytest_plugin](triton_dev/pytest_plugin/TODO.md) | collection 及 pytest 阶段事件插件 |
| [serve](triton_dev/serve/TODO.md) | loopback 登记任务 API、鉴权、队列/取消/恢复/SSE、可选同源前端 |
| [common](triton_dev/common/TODO.md) | 原子文件、进程组、有界流式执行与取消 |
| [cli](triton_dev/cli/TODO.md) | 统一 CLI、离线命令、参数/envelope Schema |
| [integrations](triton_dev/integrations/TODO.md) | 合成 SDK 接口、脚本模型接口和端到端演示 |
| [integrations/shell](triton_dev/integrations/shell/TODO.md) | bash/zsh 核心流程已验证 |
| [integrations/ai](triton_dev/integrations/ai/TODO.md) | provider 协议已定义，离线模型已验证 |

## 本轮交付范围

- 命名组合和 Python wheel 来源混合不支持未知的原生组件混用。预检不是完整依赖求解器。
- runs 显式持久化；Server 使用独立 tasks 状态目录，单 worker 保守调度。
- AI 使用脚本模型，skills 保存在仓库 skills/，未全局安装。
- 离线接口、配置与限制见 docs/OFFLINE.md；examples/offline_demo.py 可复现实例。
- 尚未交付：真实 SDK/内部认证/设备验证、原生 ABI、实际编译、实时模型、自适应根因定位与远程多人服务。网页已实现可交互演示及真实登记任务 API，其余环境/诊断 HTTP 服务待接入；pytest 用例服务见下方增量。

## 前端

- frontend/：按选定设计实现浅色/青绿工作台、组合抽屉、用例筛选、运行详情、诊断与设置。
- 默认演示模式明确标记；真实接入限已登记任务的查询/提交/取消/状态事件。凭据仅存页面内存。
- serve --ui 可静态服务构建后的 frontend/dist/client；同源 Origin 合法、跨源仍拒绝。
- 操作与接入说明见 frontend/README.md。

## 验证记录

- v0.2 本轮：本机 Python 3.14 / macOS 完整测试 87 passed；最终命令 Schema 调整后相关 CLI 测试 5 passed。ruff、差异空白检查、sdist/wheel 构建通过，两个 SKILL.md 通过 skill-creator 校验。端到端 mock 演示及仓库外 installed-wheel smoke（离线组合安装、探测、真实执行、pytest 阶段和证据包）通过。Linux/Python 3.10/3.12 尚未在本机验证，CI 已补充离线依赖供给与安装包闭环。

- 2026-10-23 续作：修正 prepare 忽略 --python 的问题；使用选定解释器创建 venv，安装前核对版本/平台，保留解释器软链接路径。准备协议升级为 v2，旧缓存不会误复用，旧目录不自动删除。增加真实子进程的带空格路径、PATH 查找及创建失败测试。跨 Python 版本和真实 SDK 验证仍待接入。
- 本次续作验证：Python 3.14 / macOS，完整离线测试 51 passed；ruff 通过；sdist/wheel 构建成功；安装 wheel 后在仓库外验证 import、capabilities、describe、doctor、prepare help。当时 setuptools 提示测试目录的 package-data 配置歧义；本轮已通过显式 include-package-data=false 整理，v0.2 构建不再出现该告警。

- 本地：Python 3.14 / macOS，合成 SDK、真实本地 HTTP、pip/venv、bash/zsh、pytest collection 和并发子进程。
- Linux/Python 3.10、3.12、3.14：由 GitHub Actions 的 offline-ci 持续看护；最终结果以 workflow 为准。
- 真实 SDK、编译、设备和 AI：TODO，接入条件见 docs/INTEGRATION.md。

- 前端收尾：88 项 Python 测试与 ruff 通过；前端模型/静态打包测试各 4 项通过。sdist/wheel 构建及仓库外安装 smoke 通过。桌面源图对照、390px 窄屏与 1024px 平板布局、真实任务成功/取消和控制台检查已完成，详见 frontend/design-qa.md。Python sdist 包含前端源码，wheel 不捆绑网页构建。

## pytest 服务增量（未提交）

- 登记 pytest 项目真实收集、参数化 nodeid/markers/fixtures/逻辑ID查询与选择运行。
- 默认逐 case 独立进程，可切换整次 session；源码复制、独立 HOME/tmp/编译缓存，保留源码 SHA256 和解释器包版本，漂移时拒绝运行。非容器沙箱，设备/网络/绝对路径/解释器目录仍共享。
- 网页呈现真实阶段、统计、捕获输出、context、显式附件与原始记录；失败项/全部复测生成新 ID 和 parent，并比较所选用例前后状态。
- CPU 工作流样例不验证真实 kernel；设备租约、原生 ABI、多任务并发、多用户、HTTP 参数覆盖与大历史分页仍待实现。配置和接口见 docs/PYTEST_SERVER.md。

- pytest服务验证：Python 3.14/macOS 完整97 passed、ruff通过，前端模型/静态打包各4项通过；构建与仓库外安装smoke（含服务收集/运行/复测）通过。覆盖隔离污染、setup/call/teardown、skip/xfail/xpass、取消/incomplete、源码冻结、包版本漂移、元数据重复、嵌套/带空格/别名路径、附件链接限制与真实HTTP。浏览器实际运行8项并失败项复测3项，390px结果页复验通过。HEAD保持3ec8de2，增量未提交。

## 单服务器多人平台目标（设计，未实现）

- 已确认：sudo管理部署；姓名进入、无密码；用户选择环境组合、指定case、获取报告。
- 设计采用name-only协作归属；同名可进入相同工作区，不把姓名当可验证身份或管理员权限。API/Builder/Runner分离，case不以root运行；最新环境用不可变revision与可更新别名发布，任务固定快照。
- 目标架构、接口、资源与迁移顺序见 docs/MULTI_USER_SERVER.md。当前运行中的仍为本地loopback/Bearer原型，未切换生产身份、数据库或容器后端。

## 参数配置与 xdist 增量（未提交）

- 已实现：逻辑用例分组与参数实例单选/多选；单次运行 xdist workers、每 worker 日志/进度/PID/独立缓存；失败复测保留 workers 与扩展选项。
- 扩展接口：服务登记 schema/default/version/固定编译函数，项目 allowlist；内置失败阈值、慢阶段统计和输出捕获。HTTP 不接受自由命令。
- xdist 同次运行共享源码工作目录，设备尚无租约；默认逐 case 模式保留。远程多用户身份及任意 fixture 参数覆盖仍待实现。
- 验证：Python 105 passed、ruff通过；前端模型5项和静态打包4项通过。详细使用及边界见 docs/PYTEST_SERVER.md。

- 本轮安装验证：sdist/wheel构建、仓库外安装smoke通过，包含真实两worker xdist与原有收集/执行/复测。浏览器39通过+1预设失败，配置单选及每worker日志可见；HEAD仍为3ec8de2，无新增提交。
