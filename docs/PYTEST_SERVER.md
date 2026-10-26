# pytest 服务：收集、隔离、结果和复测

当前实现用于单机受信任测试项目；HTTP 仍绑定 loopback、Bearer 鉴权，任务队列串行调度，单次运行可用 xdist 多进程。真实 Triton / LLVM / cmodel / 设备尚未接入。浏览器中的 `pytest-demo` 是真实 pytest 进程运行的 CPU 工作流样例，断言失败是有意设置的，不代表 kernel 数值验证。

## 登记和运行

工具自身与测试解释器分开。测试解释器需要已安装 pytest 和相应 SDK 依赖，服务不会临时 pip install 或修改 venv。每种 SDK/依赖组合建议登记一个单独项目入口，解释器指向准备完成且不再原地升级的 venv。

jobs.json 的 pytest 入口示例（替换绝对路径）：

```json
{
  "correctness-sdk-a": {
    "kind": "pytest",
    "argv": ["tests/correctness"],
    "cwd": "/absolute/test-project",
    "python": "/absolute/prepared-sdk-venv/bin/python",
    "timeout": 300,
    "isolation": "case",
    "plugins": [],
    "max_workers": 8,
    "allowed_extensions": ["max_failures", "durations", "capture"]
  }
}
```

入口不能包含自由选项、绝对测试目标或 `..` 路径。可选择项目内路径、相对 nodeid。第三方 pytest 插件默认不自动加载；需要的插件由管理员在 `plugins` 登记 import 名称，conftest 正常加载。pytest 配置文件的选项仍属于受信任项目代码，网页不能编辑它们。

```bash
# 先在当前终端设置 TRITON_DEV_SERVER_TOKEN，长度至少16字符
triton-dev serve --jobs /absolute/jobs.json --ui frontend/dist/client --port 8765
```

网页设置中连接 → 用例与运行 → pytest 项目 → 开始收集 → 展开逻辑用例 → 勾选配置 nodeid → 选择隔离方式和 Workers → 运行所选配置。可筛选 nodeid、marker、参数，并展开位置、逻辑 case_id、fixtures。收集记录可切换，最近失败按同一源码快照统计。

本地 CPU 样例生成器不会访问私网或真实 SDK：

```bash
python examples/pytest_server_demo.py --workdir /new/pytest-demo-directory
# 使用输出的 jobs.json 启动服务；工作目录必须是新目录
```

## 结果怎样呈现

| 区域 | 内容 |
| --- | --- |
| 总览 | total、passed、failed、skipped、xfailed、xpassed、incomplete、pending、running |
| 用例列表 | 参数化 nodeid、最终状态；点击查看该 case 的阶段 |
| 阶段面板 | setup/call/teardown 状态、耗时、失败堆栈、累计捕获 stdout/stderr、properties、context |
| Worker 日志 | 真实 gwN、PID、状态、配置数、通过/失败数；按 worker 筛选输出，controller 单列 |
| 进程日志 | 执行中的已写入输出，完成后的有界日志尾部；pytest 捕获内容查看阶段报告 |
| 环境与源码 | 源码 SHA256、解释器、Python/平台/安装包版本、隔离方式、原始选择 |
| 附件与证据 | 显式附件下载、JSON 报告导出；原始路径和日志不自动脱敏 |
| 复测对照 | 父运行 ID、本次选择范围内的 before/after 状态和失败阶段 |

用例状态由各阶段合成：setup 或 teardown 失败优先于 call 通过；缺少完整报告不计 passed。进程退出码、运行终态与 case 状态分别保存。取消、超时、进程崩溃或服务重启后，没有完成报告的用例标为 incomplete，未执行项不会补造 passed。收集失败有独立 collection_error；空收集表示收集操作完成，不能视为任何用例通过。

服务端实时读取阶段 JSONL，网页每 1.5 秒刷新；沿用原任务 API 的 SSE **状态事件有限批次**，不宣称 SSE 已逐条推送所有 pytest 阶段。终态阶段与附件由持久文件恢复，服务重启不会自动补跑中断任务。

## 隔离怎样做

| 层次 | 当前行为 | 边界 |
| --- | --- | --- |
| 源码 | 收集时复制项目并计算内容/相对路径 manifest；运行和复测使用该冻结副本 | 复制期间应避免编辑源目录；不等于 Git/文件系统原子快照 |
| session 模式 | 每次运行启动独立 pytest 进程，共享本次 session fixture、模块状态与工作目录 | 适合高吞吐，不能阻止本次运行内 case 污染 |
| xdist 模式 | 单次 pytest 调用，`-n N --dist load`；每个 worker 独立 HOME/tmp/编译缓存与附件目录 | 同次运行的源码工作目录共享；session/module fixture 在各 worker 内复用，非逐 case 完整隔离 |
| case 模式（默认） | 每个参数化 nodeid 启动独立 pytest 进程和独立源码副本 | session/module fixture 会反复初始化，启动及复制成本更高 |
| 目录和缓存 | HOME、TMPDIR/TMP/TEMP、XDG cache、Triton/CUDA cache、pytest cache/basetemp 分开 | case 写硬编码绝对路径仍会共享宿主文件 |
| 进程变量 | 保留 PATH、locale、设备可见性和明确 SDK 管理变量；不继承服务令牌、任意私有环境变量 | 不是容器或恶意代码沙箱；需要额外运行配置的项目须适配 |
| Python 依赖 | 固定登记解释器，收集时记录 Python/平台/安装包版本，运行前检查漂移 | 不复制 site-packages；同版本二进制替换、执行期间原地改包和原生 ABI 未覆盖 |
| 设备和外部服务 | 单 worker 串行调度本服务内任务 | 外部进程、设备、端口、网络、数据库均无排他租约 |

源码快照跳过 .git、虚拟环境、node_modules、缓存和 .env 类文件；其他符号链接显式拒绝。源码项目必须不包含服务状态目录。预算为项目 100 MiB/10000 文件、收集 2000 cases、每次最多选择 500 项、源码副本合计估算 1 GiB；超限应收窄测试项目、选择 session 模式或拆批。

长期运行时建议：每个 SDK 指纹一个不可变 venv / 容器镜像，任务独立 workspace，硬件调度增加 device lease / 健康探测 / 失败后恢复，再允许共享硬件并行。cmodel 崩溃或设备状态污染不能靠重启 Python 自动证明已经清理。

## 复测怎样做

- **仅复测失败项**：收集 setup/call/teardown 中明确 failed 的 nodeid，沿用原收集源码快照、解释器、包版本期望、隔离方式、workers 和扩展配置，生成新 run_id 与 parent。首次失败不覆盖。
- **原配置全部复测**：适合取消、崩溃、超时或没有明确失败报告的运行，仍使用原源码快照。
- 要验证修改后的 case，或升级依赖后的环境，必须**重新收集**，生成新的实验；旧快照复测不会偷偷使用最新源码。
- 解释器包版本发生漂移时返回 ENVIRONMENT_CHANGED；旧源码快照内容被修改时返回 SOURCE_CHANGED。
- 复测对照只涵盖本次选择的 case；单次由失败变通过只是本次恢复观察，不自动断言 flaky 或根因归属。

## conftest / debug hooks

显式加载 `triton_dev.pytest_plugin` 后，case 可直接使用下列 fixture，不必向全局 conftest 加 autouse：

```python
def test_kernel(triton_dev_context, triton_dev_artifact_dir, record_property):
    triton_dev_context.update(shape=[128, 128], dtype="fp16", seed=42)
    record_property("component", "compiler")
    # 仅显式写入的附件列入服务端下载清单
    (triton_dev_artifact_dir / "repro.json").write_text('{"seed":42}')
    assert actual_result == expected_result
```

业务 hook 可在自己的 conftest fixture 中往 context 写容差、最大误差、首个失败坐标、设备信息等。工具不会捏造这些值，也不会自动上传 tensor。阶段堆栈最多 32 KiB，捕获 stdout/stderr 各最多 16 KiB，原始进程日志各最多 8 MiB。附件列表上限 1000，每个 HTTP 下载最多 10 MiB，拒绝跟随符号链接，不开放任意宿主文件下载。

pytest 的三阶段报告依据 [官方 hook 文档](https://pytest.org/en/stable/reference/reference.html)，临时目录机制依据 [官方 tmp_path 文档](https://www.pytest.org/en/latest/how-to/tmp_path.html)。本服务额外实现源码复制、逐 case 进程及复测 lineage。

## 后续扩展

- 分页/增量查询、SQLite 索引、保留期限和磁盘配额；当前本地原型会返回任务详情，长历史大量 case 不适合无限累积。
- 环境制品哈希验证、不可变容器 runner、设备资源租约和恢复策略。
- 受控 fixture 输入覆盖；当前扩展参数 schema 已实现，但 case 参数只能选择已经收集的实例，不能从网页改写源码。
- 重复实验的稳定性统计、原始日志脱敏证据 ZIP、多用户权限。

## 配置选择和 xdist workers

逻辑用例按 pytest 原始函数/类路径分组，展开后逐项显示真实参数化 nodeid；32 个配置中可只勾选一个。逻辑 case_id 用作业务标记，不用于合并不同函数。筛选时组选择只影响可见配置，隐藏选择保留；底部显示本次实际配置总数。

选择 40 个配置，设置 Workers=4，会切换到 xdist 模式并交由四个测试进程动态调度，另有一个 controller。实际分配不保证每个 worker 恰好十个。case/session 模式只允许 workers=1。项目 max_workers 默认8，管理员可设1..32；测试解释器必须提前安装 pytest-xdist，缺少时显式报错，不自动安装。xdist 自身插件由服务固定加载。

worker 崩溃不自动重启或隐式重跑；未完成报告保留 incomplete。取消/超时会终止整个进程组。单次运行的 worker 数不表示设备数，设备租约尚未实现。

每个 worker 日志磁盘上限8 MiB，页面展示尾部64 KiB并标记截断。pytest 捕获的 stdout/stderr 在阶段结束后写入；需要执行中进度时使用 `triton_dev_log("正在编译...")` fixture 主动写入。普通 `-s` 不提供 xdist worker 实时 stdout 转发。参见 [xdist 分发](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)、[worker 标识](https://pytest-xdist.readthedocs.io/en/stable/how-to.html)、[已知限制](https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html)。

离线 CPU 并行样例：`python examples/pytest_parallel_demo.py --workdir /new/parallel-demo`，包含32+8配置，有意设置一个断言失败。

## 扩展运行配置接口

GET `/api/pytest/extensions` 返回 schema_version=1 和服务器登记项，GET `/api/jobs` 返回项目允许的扩展 schema、默认值、版本及 max_workers。网页据此生成表单。目前内置 max_failures（0..100，0不限）、durations（0..100，0关闭慢阶段统计）、capture（fd/sys）。并行达到失败阈值时，已经运行的配置可能继续完成。

```json
{
  "collection_id": "run_collection_id",
  "nodeids": ["test_kernel.py::test_matmul[fp16-128]"],
  "isolation": "xdist",
  "workers": 4,
  "extensions": {"max_failures": 0, "durations": 10, "capture": "fd"},
  "idempotency_key": "new-run-key"
}
```

受信任服务器启动代码可调用 `triton_dev.execution.options.register_extension(RunExtension(...))`，注册整数/布尔/字符串 schema、默认值、版本和固定 argv 编译函数；jobs.allowed_extensions 控制项目开放范围。新的 pytest 选项还需登记受信任插件。HTTP 不接受自由 shell/pytest argv 或插件上传。规范化选项和扩展版本写入原始运行记录，复测复用；版本变化拒绝执行并要求创建新配置。此接口用于后续 seed、诊断级别等扩展，不自动推断 fixture 参数覆盖。

受信任扩展示例（在服务器初始化 TaskManager 前注册，然后加入项目 allowed_extensions）：

```python
from triton_dev.execution.options import RunExtension, register_extension

register_extension(RunExtension(
    name="traceback_style",
    title="堆栈显示",
    description="选择 pytest 失败堆栈长度",
    schema={"type": "string", "enum": ["short", "long"]},
    default="short",
    compile=lambda value: ["--tb", value],
    version=1,
))
```

注册值只在当前服务进程有效，重启时须由同一启动代码恢复；网页表单自动发现项目允许的登记项。
