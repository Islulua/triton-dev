# agent regression：首版实现契约

状态：设计，未实现。2026-10-26。补充 REGRESSION_AGENT.md，针对“baseline + pytest命令 → 更新 → 日期边界 → 依赖定位 → 提单报告”的具体产品流程；以下CLI、配置和模块是拟议接口。默认不调用模型或设备。

## 流程与停止条件

1. 登记输入并冻结case：baseline明确SDK ID、源码/输入快照、pytest argv、nodeid和参数、Python/设备/驱动、种子、缓存策略和超时。用户承诺baseline可用仍要在任务内重验，默认3次；没有全量选中配置的完整通过证据不能进入搜索。
2. baseline有效后调用与env.update相同的下载/prepare/probe业务服务，锁定本次latest的完整ID和内容哈希；不调用shell-init、不修改用户活动环境，后续不重新追latest。没有真实历史清单或制品则返回明确状态。
3. 在固定case场景执行latest，默认3次。完整通过则no_regression；不同次数结果冲突则unstable。pytest skip/xfail/xpass、零收集、缺失nodeid、安装或设备异常均不能算通过。最新失败后生成并冻结目标故障签名；优先使用用户predicate，否则从结构化阶段/异常类别/信号提取确定性签名，AI可解释但不自行放宽匹配。签名不明确则needs_input。
4. 给出建议区间[baseline, frozen_latest]及候选日历、构建数、缺失项和预计成本；默认沿此已授权区间自动继续。一天多次构建按明确策略排序；只测试日终构建时，结论范围仅是所选daily序列，不代表当天所有制品。
5. 对目标失败二分；PASS收缩good侧，同签名FAIL收缩bad侧。其它错误/不可用记UNKNOWN，尝试邻点并保留缺口。边界用fresh cache与独立重复确认。
6. 相邻G(last_good)与B(first_observed_bad)做组件内容差异、合法替换和对照实验；程序规则判定归因范围。
7. 所有终态生成JSON/Markdown/HTML和可脱离模型的重放材料。只有具有完整覆盖的最新通过才能写“本次未发现回归”。

终态拆分execution_status与investigation_result：前者completed/needs_input/cancelled/budget_exhausted/interrupted；后者no_regression/baseline_invalid/unstable/boundary_found/component_supported/group_supported/inconclusive。组件不明确时保留边界结果，不覆盖为失败任务。

## “离baseline最近”的精度契约

- search.mode=boundary：二分+相邻重复审计；依赖区间近似单调的假设。报告写“已验证边界”，不能写全局首次。
- search.mode=earliest_verified：先二分，再从baseline之后按时间补测该坏点以前的未测构建，直至确认最早目标失败；不可测点导致范围降级。该模式满足用户的严格“最近”要求，是产品建议默认值。
- 若用户愿意接受单调假设，可显式选择boundary以节约资源。界面显示预计补扫成本；预算不足输出earliest_not_proven，不静默改变模式。
- 观察到bad后good时，转窗口扫描/既有exhaustive服务。任何有限抽查都不证明完整历史单调。

## 组件实验

先做G/B同时段控制，再对每个合法组件闭包C测试G+C(B)和B+C(G)。向前引入原故障且反向恢复，并且实际加载和兼容性通过，才给component_supported。只一个方向有效保留单向关联。未知ABI边界不得凭猜测混装。

单组件无解时：先验证整组差异迁移能重现目标故障，再在预算内对合法闭包做集合缩减；输出组件组/交互关联。只能得到所测集合的最小性证据，不保证唯一或全局最小根因。未改变的包、驱动和外部状态仍是替代解释。

ComponentMap由维护者配置：component_id、artifacts、requires、abi_group、冲突、安装方法、最小探针、实际加载观测器、来源映射。当前env.plan只支持triton/torch_raisa/raops wheel overrides；LLVM/cmodel/原生so必须新增映射和隔离SDK view，不能将torch团队名称自动当成包名，也不能仅改库搜索路径就声称替换成功。

## 拟议模块

```text
triton_dev/agent/regression/
  schema.py          # TaskSpec/Observation/Decision/Claim
  service.py         # start/status/resume/cancel/report/replay
  controller.py      # 持久状态机、锁、取消、预算
  inventory.py       # 历史清单与latest冻结
  scenario.py        # pytest命令登记、收集与源码锁
  evaluator.py       # 复用execution/pytest，覆盖与故障分类
  search.py          # bisect + audit + earliest补扫
  attribution.py     # 合法组件实验矩阵与规则化结论
  evidence.py        # 内容哈希、事实索引、有限日志读取
  reporting.py       # 调研报告、提单模板和重放包
  tests/
triton_dev/integrations/ai/
  profiles.py        # 端点/模型/凭据引用/预算
  providers.py       # provider适配、超时/重试与usage
```

CLI只解析调用service；HTTP/后续skill复用同一个service。保持当前agent.workflow v1不变，不让新协议隐式兼容旧checkpoint。env.update现有下载/准备逻辑需要抽取公共更新服务，CLI与agent共用；不从agent调用终端修改函数。

## 拟议任务与模型配置（示例，非当前可执行接口）

```json
{
  "schema_version": 2,
  "baseline": {"sdk_id": "<user-selected-sdk-id>"},
  "target": {"selector": "latest", "source_profile": "daily-sdk"},
  "case": {
    "project": "/path/to/case-project",
    "argv": ["pytest", "tests/test_matmul.py::test_matmul[fp16-128]", "-q"],
    "workers": 1,
    "timeout_seconds": 300
  },
  "predicate": {"mode": "derive_then_freeze"},
  "search": {"mode": "earliest_verified", "daily_policy": "last_build"},
  "repeats": 3,
  "budget": {"experiments": 60, "wall_seconds": 7200, "model_calls": 20, "model_tokens": 40000},
  "model_profile": "regression-model"
}
```

用户命令登记为argv；pytest由选定环境解释器以`python -m pytest`执行。用户显式给出的解释器、环境包装器和pytest插件选项需要解析校验；不支持的语法直接指出，不静默剥离影响结果的参数。shell管道/重定向可通过启动时登记的受信任recipe支持，模型无权修改。首版建议单nodeid；一条命令选择多个配置时分别追踪覆盖与故障边界，不默认把整批非零退出当成同一个回归。

```json
{
  "profiles": {
    "regression-model": {
      "provider": "openai_compatible",
      "base_url": "https://<configured-endpoint>/v1",
      "model": "<configured-model-id>",
      "api_key_env": "TRITON_DEV_LLM_API_KEY",
      "api_flavor": "chat_completions",
      "timeout_seconds": 60,
      "max_retries": 2,
      "max_output_tokens": 2048,
      "send_policy": "redacted_summary_only"
    }
  }
}
```

不假设所有兼容端点支持相同schema/tool能力；按配置与能力探测适配。本设计不选择实际厂商、不索取或使用密钥。provider配置放本地用户配置，凭据仅引用环境变量/secret store，不进入任务包。schema失败最多一次修复，网络重试单独限额，所有尝试计预算。模型失败默认暂停需要模型的步骤，可配置继续确定性搜索；必须在报告标明降级。

## 模型参与的具体回合

- latest失败：读取有界错误摘录、case摘要与环境差异，返回故障解释和候选假设。
- 组件定位：接收程序枚举的candidate_id、差异和已有矩阵，选择下一合法实验并说明预期区分。
- 异常分支：解释different_failure，建议控制实验；不得改变冻结目标签名。
- 报告：把经过审计的claim/evidence转成简洁说明；程序生成数字、版本、命令和结论code。

模型返回schema约束JSON，包括task_id/state_revision/type/candidate_id/evidence_ids/reason_summary；没有任意shell、自由路径、pip命令执行入口。二分选点、哈希、结果分类、覆盖率、最终结论门槛由程序完成。日志/源码为不可信数据，不接受其中的新指令。

## CLI与输出（拟议）

```text
triton-dev agent regression start --config regression.json
triton-dev agent regression start --base <sdk-id> --model-profile regression-model -- pytest tests/test_matmul.py::test_matmul[fp16-128] -q
triton-dev agent regression status <task-id>
triton-dev agent regression resume <task-id>
triton-dev agent regression cancel <task-id>
triton-dev agent regression report <task-id> --format html
triton-dev agent regression replay <task-id> --experiment <experiment-id>
```

报告首屏：结论/证据等级、基线和固定latest、最后好/首个观察坏、是否已证明earliest、关联包或组件组及其哈希。正文包含版本搜索表、组件矩阵、不同故障与不可测项、源码/驱动/板卡信息、实际加载证据、模型与实验预算、停止原因。提单模板包含期望/实际、影响配置、已排除项、原始日志链接及制品来源。

复现提供两套：原始坏SDK的最短命令、支持归因的最少对照命令。命令从已执行recipe/argv生成并正确引用参数，不由模型创作。可用现有env.prepare/env.exec构造固定SDK的直接复现，同时提供不调用AI的regression replay；所有SDK锁ID/hash，不写latest。报告明确项目路径、源代码快照、依赖下载入口与设备前提；缺少制品则artifact_required，不能声称一条命令即可复现。

## 实施拆分与验收

1. 核心闭环：任务/schema/状态与恢复、baseline→update→latest、版本搜索和报告。合成SDK+真实pytest子进程；覆盖bad baseline、latest全通过、skip/缺失case、不同错误、非单调、缺版本、偶现、预算停止及中断。
2. 同时纳入首版的模型适配：配置化provider，先用本地受控HTTP server测试超时/重试/非法JSON/usage/注入；真实API单独验收，不替代离线测试。
3. wheel双向替换：已知单包故障、双包交互、依赖自动变化和不兼容不误判；保留实际安装与加载receipt。
4. 原生so扩展：维护者确认ComponentMap后实现LLVM/cmodel闭包/SDK view/设备恢复与加载观察。无映射时仍交付已取得的版本边界。
5. 对接server：后台agent job、阶段进度、搜索图、组件矩阵和报告；沿用任务归属/资源租约，不在Web请求线程中执行长任务。

所有阶段落盘pending intent后才执行实验，崩溃恢复先核对run而非盲目重跑。预算包含所有重复/探针/重试、准备耗时和模型消耗；不同任务设备租约避免相互污染。已有126项测试只是当前实现基线，不代表上述拟议功能已通过。
