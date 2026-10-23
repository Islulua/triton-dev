# triton-dev 设计与实现

## 第一部分：基本设计

### 目标与原则

统一 CLI + Python 服务 API。人通过候选菜单/显式参数，CI 使用非交互 JSON，agent 通过白名单 CLI Bridge；功能规则只实现一次。工具自身与 SDK 测试 Python 环境分开。普通查询不修改 SDK，环境选择不使用全局 current。

先完成确定性逻辑；AI 仅提出候选动作和解释，代码拥有状态、预算、真实观察与执行权。工具成功、case 通过、目标故障复现是三种不同概念。

### 边界与调用

| 模块 | 负责 | 禁止的隐式行为 |
| --- | --- | --- |
| env | SDK 解析、下载、包组合、变量和 venv | 自动改源码/重编仓库、覆盖活动环境 |
| build | 已知源码目标与构建输入 | 自动 checkout/reset、切换终端 |
| cases | pytest collection 的真实候选 | 将收集错误当空列表成功 |
| execution | 参数数组启动进程、超时、原始结果 | 根据非零退出码直接宣称目标回归 |
| diagnosis | 固定判据和 good/bad 对照 | 将环境错误当同一故障 |
| agent | 状态机、问答、工具编排 | 执行模型自由 shell、伪造证据 |
| reporting | 整理已有证据 | 暗中重跑或自动对外提单 |
| doctor | 只读预检 | 自动修权限/安装 |
| serve | 本地只读发现原型 | 任意命令/文件 HTTP 接口 |

env 发现重编需求时由上层显式调用 build，不构成循环。各服务支持可注入路径/适配器，生产默认仍集中在 settings.py；跨 CLI 不假设共享内存。

### 状态与文件

SDK 按 `TX82_SDK_Daily_YYYY-MM-DD-HH-MM` 解析时间，不按 mtime。latest 在调用时解析一次，执行使用固定路径。临时下载目录不参与发现，失败不发布。

准备缓存以解释器身份、SDK 路径、精确 wheel 与哈希组成 key。venv 在最终目录创建，离线安装后写一个内部 ready.json；不移动 venv，不覆盖不完整/使用中的环境。失败目录需显式检查和移除。默认不生成用户报告或组合 YAML。

原生 SDK 文件可能共享 lib；不能通过 lib 顺序宣称切换了一个组件。原生 ComponentMap 和组合视图尚未实现，明确拒绝。wheel 覆盖只接受已知 Python 包。仅路径模式必须显式 native-only，并携带 not_checked。

### 命令与测试

argparse 定义是当前 CommandSpec 的唯一来源，describe/capabilities 从相同 parser 生成。完整 schema/候选搜索/UI 属后续改进，不把当前轻量描述称为完整 JSON Schema。

每个模块有 tests、TODO.md 和进度。离线 CI 不访问内部 JFrog，不调用真实模型，不依赖设备。固定 SDK 集成缺条件时必须独立报告未完成，而非把 mock 结果当真实 SDK 通过。

## 第二部分：模块介绍、功能、实现和测试

详细进度与验收条件分别维护在各模块 TODO.md，集中索引见 STATUS.md。

### env

介绍：输入固定根目录中的 SDK。功能：discover/select/inspect/diff/download、plan/prepare/resolve、export/probe。实现：目录模式、wheel ZIP 元数据、SHA-256、HTML 列表、事务下载、离线 venv、POSIX 文件锁。测试：日期、歧义、不完整最新、并发下载、安全解压、合成 wheel 真安装、转义和进程隔离。

已知接口：ENABLE_CMODEL=1；RAISA_FW_PATH、RAISA_C_TOOLCHAIN_PATH、RAISA_CMODEL_PATH 均为 SDK 根目录；LD_LIBRARY_PATH 明确为选定 lib。PATH 通过原始基线生成，切换不反复叠加。

### build

介绍：多仓统一入口。功能：.repo 工作区发现、六个源码目标、只读 plan。实现：静态目标登记表，不执行未确认编译脚本。测试：实际路径发现与缺目标错误。具体编译留待接入，见 build/TODO.md。

### cases 与 pytest_plugin

介绍：真实 pytest collection。功能：参数化 nodeid、路径、markers。实现：独立进程显式加载插件，通过受管临时输出传回结构化数据。测试：参数化、收集错误、测试体未执行。导入测试代码仍可能有副作用，不等于完全无副作用。

### execution

介绍：运行明确命令。功能：环境注入、临时缓存、stdout/stderr、退出码、超时及进程组取消。实现：Popen(argv, shell=False, start_new_session=True)。测试：真实并行进程、不改父环境、非零退出码、超时。

### diagnosis

介绍：确定性回归对照。功能：重复 good/bad；good 失败即停止；显式输出片段与非零退出共同构成基础故障判据。实现：固定 SDK 路径，调用 env/execution，返回 evidence 与 SDK 范围结论。测试：target/different failure、baseline invalid、真实脚本对照。组件/仓库归因尚未支持。

### agent

介绍：Python 控制器 + 模型协议。功能：离线 ScriptedModel、只读 CLI query、ask_user、finish、轮次预算。实现：严格字段/任务/轮次/动作/证据检查；固定参数数组调用真实 CLI；重复查询停止；只读观察不能 finish 为某仓库有 bug。测试：真实 CLI Bridge、未知证据、自由 shell、断言修改和不充分结论被拒绝。

实时 AI provider、实验动作与 agent regression 仍返回 UNSUPPORTED。离线协议用于将来 provider 接入，不通过 mock 伪装实时智能定位。

### reporting / doctor / serve

reporting 聚合已有实验，doctor 只读检查路径与 shell，serve 只读 loopback capabilities。各自有真实单元/HTTP 测试。任务调度、持久化、SSE、网页、权限及 agent 回答流程均为后续。

### CLI / integrations / common

CLI 参数和帮助统一，JSON envelope 明确，交互提示走 stderr。shell-init 输出可信代码，在成功导出后才 eval；安装入口用绝对路径，deactivate 恢复原受管变量。AI live provider 不在 v0.1 接入。公共文件锁、原子 JSON 和进程执行分别测试。
