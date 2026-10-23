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
- 尚未交付：真实 SDK/内部认证/设备验证、原生 ABI、实际编译、实时模型、自适应根因定位与远程多人服务。网页已实现可交互演示及真实登记任务 API，其余环境/用例/诊断 HTTP 服务待接入。

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
