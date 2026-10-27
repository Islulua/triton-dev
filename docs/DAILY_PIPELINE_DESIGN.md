# Daily SDK 构建、测试与质量日历设计

状态：完整目标设计，2026-10-27，基于提交 `680d733`。首版Mock SDK/环境 + 真实CPU pytest、日历、报告、数据库日志和API/CLI已实现，实际可用范围见 [DAILY_USAGE.md](DAILY_USAGE.md)。本文更完整的生产机制仍有待实现项；旧 `platform manage daily-*` 保持元数据 / 登记环境演示模式。

## 1. 范围与复用

目标：每天发现最新完整 SDK，冻结版本，构建并验证独立环境，运行指定 pytest 集合，将质量日历、逐配置报告和完整日志统一入库。网页与 CLI 操作同一个服务，Agent 不通过页面抓取或直接 SQL 执行任务。

| 已有能力 | 本轮设计如何复用 / 扩展 |
|---|---|
| SDK 下载、哈希与安全解压 | 增加来源/平台/轨道选择、发布完整性与新鲜度判据、任务化日志 |
| `env.prepare` 独立 venv、解释器身份检查、内容key | 增加不可变 environment_revision、环境健康探针和DB构建步骤；不原地更新已使用环境 |
| 登记项目、源码快照、真实 collection、xdist | 固定 suite_revision + collection，Runner从已验证环境revision获取解释器，而非一直使用登记时的旧Python |
| 逐配置结果、阶段、worker报告、复测 | 规范化结果归类、补充批次关联与多维查询；保留现有报表和FAIL/CRASH色块 |
| SQL队列、generation、租约、取消、checkpoint | 扩展为分阶段持久流水线和资源租约，不用Web进程内定时器充当唯一调度依据 |
| 个人workspace、system、证据索引 | 系统Daily与个人复测分开归属，公共报告显式发布 |
| 当前 SDK 元数据 / daily 批次 | 迁移到新模型；旧记录保留 `registered_job_environment`，不能标记为真实SDK Daily |

## 2. 对象与一次执行

- **Daily definition**：人类可读计划，如 `tx82-main`。
- **Definition revision**：不可变来源选择器、配方、suite、时间、门禁与资源配置。
- **Schedule occurrence**：计划的一次业务日期触发；唯一键 `(definition_id, business_date, schedule_slot)`。
- **Batch**：该次触发的主流水线，包含SDK、环境、源码、收集、执行与报告关联。
- **Attempt**：首次执行或完整重跑的一次尝试。重跑不更新旧attempt；流水线阶段的技术重试另记step_attempt。
- **Run / case result**：具体测试子任务和每个参数配置的唯一最终结果。
- **Quality publication**：日历当前引用的完整attempt及其指标、policy revision、计算版本；历史引用变化可查。

业务日期使用计划时区（默认Asia/Shanghai），执行时间记录UTC。跨午夜结束仍属于原业务日期。多套计划、多Python、板卡和suite必须独立维度展示，不把不可比较的环境混算。

## 3. 持久流水线

```mermaid
flowchart LR
  A[计划触发 / 手动补跑] --> B[发现并冻结最新SDK]
  B --> C[下载 / 哈希 / 安全解压]
  C --> D[构建独立环境revision]
  D --> E[解释器 / 导入 / 原生与设备门禁]
  E --> F[冻结源码与pytest collection]
  F --> G[指定集合 / xdist执行]
  G --> H[汇总与校验结果完整性]
  H --> I[原子发布报告与日历状态]
  I --> J[更新通过门禁的环境别名]
```

阶段状态：`queued → running → succeeded | failed | cancelled | interrupted`。批次另有 `waiting_sdk` / `waiting_resource`；质量结论独立于执行状态。一个 `completed` 任务可能是质量红色。

### SDK选择与下载

1. 计划引用服务器登记的 `source_id + channel + platform`，不能从整个目录随机选最新记录。
2. 以可信构建序号/发布时间排序，要求 manifest 完整且制品发布完成；同日多构建靠构建标识区分。无法唯一排序则返回 `AMBIGUOUS_SDK`，不按随机UUID决定最新。
3. 默认等待当天新SDK到配置的 `sdk_deadline`。超时为 `NO_NEW_SDK`，当天红色；复用旧SDK须显式配置并在报告标记，不能静默假装更新成功。
4. 一旦选定，冻结build_id、组件版本、内容SHA256、发现截止时间和来源证明。执行过程中出现更新SDK不切换本批次输入。
5. 下载到临时区，完整校验后原子登记。来源没有可信校验信息时返回明确的 `unverified_source`；不能把自己算出的digest描述为上游可信认证。
6. 缺包、校验失败、下载错误进入构建/制品失败类别，不制造一个假的case失败。

### 环境制作与使用

- 环境key由SDK内容、依赖锁、Python身份、基础镜像/宿主要求、安装配方revision和测试工具版本组成。
- 相同key复用已验证环境；同一key并发构建去重。原生组件、驱动/固件、ABI边界在环境receipt中明确记录。
- 健康探针至少包含Python身份、包导入/版本、原生库加载；板卡suite另需设备可用性和最小设备测试。未知探针不能填写通过。
- venv已安装不等于环境已验证。只有required probes全部满足才能进入测试阶段。
- Runner使用该环境的实际解释器与冻结源码收集并执行；不能将新SDK元数据挂在旧解释器上继续跑。
- 下载、环境制作不改变个人终端、已运行环境或现有latest。分别维护 `latest_built` 与 `latest_qualified`，只有全部门禁通过才更新后者。
- 每任务独立HOME/TMP/cache；环境制品可只读共享。设备exclusive/shared由服务器登记，xdist并发数不能绕过设备容量限制。

### 指定pytest集合

suite引用登记项目、固定源码revision、测试路径、markers、nodeids、排除项和扩展配置；这些输入来自受控配方，不允许API自由拼接shell。

collection结果冻结为预期配置集合，记录collection_id与digest。收集为零、收集异常、实际启动的解释器/快照与冻结输入不一致都使Daily红色。每个参数化nodeid是一个配置，不将setup/call/teardown计为三个case。

## 4. 日历语义

页面以一个月为默认，计划选择 + 上/下月 + 今日 + 可用时的补跑入口。每格只显示日期、状态、通过/总数与耗时；保留结果文字/图标，不能只靠颜色。

| 情况 | 日历状态 | 原因 |
|---|---|---|
| 已完整结束、预期配置数>0、每个配置都是PASS、必需阶段/分片均成功且日志/结果完成确认 | 绿色 / 全部通过 | 严格全PASS |
| 终态存在FAIL、CRASH、TIMEOUT、XPASS、XFAIL、SKIP、INCOMPLETE等任一非PASS，或必需流水线阶段失败 | 红色 / 未全通过 | 展示首要原因与分类计数 |
| 运行或等待SDK/资源，仍在有效deadline内 | 蓝色 / 进行中 | 不是失败，也不是通过 |
| 未计划、未来日期或尚未到计划时间 | 灰色 / 未运行 | 不伪造结果 |
| 应执行却超过deadline仍未产生/完成任务 | 红色 / 缺失或超时 | 调度watchdog生成缺失记录，不无限显示灰色 |

**XFAIL是已知预期失败，但不是PASS，所以仍然红色**。单独显示“只有XFAIL / 只有SKIP”等原因，避免误认为有新增缺陷。即使pytest退出码为0，也不能据此把日历标绿。

### 同一天多次运行、多个suite

- 默认日历引用第一次正式Daily的完整结果；补跑/复测显示小徽标，不自动覆盖原始失败。
- 管理者可将同输入的完整重跑明确设为正式结果。该发布动作检查所有必需配置/分片、记录操作者和原因，保留原始红色历史。
- 一键“仅失败项复测”是子集，永远不能独立把当天变绿。
- 同一天出现新SDK，建立单独candidate batch并显示“2个构建”；不能把新SDK结果覆盖旧SDK报告。进入日期详情可选择具体构建 / attempt。
- 多suite日历汇总以同一个质量策略为准：全部required suite严格PASS才绿；任何required红则红；仍有待执行则进行中。disabled/optional suite明确列出，不能用用户临时筛选改变官方质量结论。
- 按板卡/Python查看时显示该范围的结论；“官方全部范围”与“当前筛选”必须区别。

## 5. 质量报告与统计口径

### 报告页面顺序

1. 日期 / 计划 / SDK / attempt选择；状态、已冻结环境。一个主操作“复测失败项”，完整重跑与下载为次要动作。
2. 六项摘要：严格PASS比例、测试通过率、失败数、执行覆盖率、测试耗时、流水线总耗时。
3. 分类条：PASS / FAIL / CRASH / TIMEOUT / SKIP / XFAIL / XPASS / CANCELLED / INCOMPLETE。
4. 质量图：按算子/模块、失败阶段、dtype/shape、Worker统计；阶段耗时、慢配置、与上个可比Daily变化。
5. 完整配置表。原始快照、调度事件、完整版本清单与口径放在折叠区。

### 配置结果与公式

归一化每个参数配置为一个互斥结果，且保留原始pytest outcome、wasxfail、strict和各阶段报告。

- `expected_count`：冻结collection内应运行配置数。若collection失败，数量未知显示“—”，不能当作0测试全部成功。
- `strict_pass_ratio = PASS / expected_count`，日历全绿要求其为100%且required阶段完整成功。
- `test_pass_rate = PASS / (PASS + FAIL + CRASH + TIMEOUT + XPASS)`；剔除XFAIL/SKIP/取消/不完整，分母为0显示“—”。该指标与严格比例并列，不能用它掩盖跳过。
- `execution_coverage = (PASS + FAIL + CRASH + TIMEOUT + XPASS + XFAIL + SKIP) / expected_count`。取消、未启动和不完整不算完整配置结果；另给 `body_execution_rate` 表示实际进入call的比例，避免把SKIP当成测试体执行。
- XFAIL与XPASS分开显示。严格XPASS即使原始pytest标为failed也只归XPASS一次，不重复计FAIL。
- 同case有多个阶段失败只计一个最终配置，保留全部failure_phases；缺少退出证据不标成CRASH，未执行项不批量标CRASH。
- 额外的“策略可接受率/质量门禁”可单独配置，但不改变用户要求的严格全PASS日历定义。

当前运行总览的旧通过率是 `passed/(passed+failed)`。Daily 上述分类契约须标记新的 `metrics_version`，明确计入CRASH/TIMEOUT/XPASS；旧报告按原口径保留，不静默改写历史数值或跨版本混算。

### 时间指标

区分触发→排队、SDK等待、下载、环境构建、健康探针、收集、测试、报告归档、端到端耗时。并行case耗时累计工时与测试墙钟耗时分开。P50/P95/TopN取有观测计时的配置，缺失值不补0。

比较上个可比批次时固定suite/source/平台口径，版本变化可比较结果回归；配置新增/删除、测试源码变化、设备变化单独标记。环境制作快慢不能直接解释为算子性能回归。

## 6. 完整表格、日志跳转与一键复测

### 配置表

默认紧凑平铺表格，支持“按文件 / 按逻辑用例”分组开关；分组默认折叠。

列：文件 / 用例 / 配置、算子、结果色块、dtype/shape、开始/结束、累计阶段耗时、worker、失败阶段、失败摘要、日志 / 复测操作。横向低频字段可进入详情，不常驻打印长ID与完整堆栈。

服务端筛选：结果多选、文件、类/用例、operator、markers、dtype、shape、worker、failure phase、时长区间、新增失败、复测变化；搜索nodeid、参数、case_id、失败摘要。精确过滤与模糊搜索分开，查询参数在URL保留。游标分页，不把整个Daily的几万配置加载到浏览器。

报告表与导出带同一快照版本。支持“当前筛选CSV/JSON”和“完整HTML/JSON”；大导出为异步任务，返回export_id。所有字段CSV转义并防止公式注入，HTML内容转义。

### 日志视图

点击某配置直接进入对应run + configuration + setup/call/teardown + worker的日志范围，默认定位首个失败事件；允许切换本case、该worker、该步骤和控制进程日志。不能只跳到几万行总日志。

并行归属不明确的控制进程输出只归控制进程，不强行绑定case。支持时间、等级、关键词、worker、阶段过滤、前后文加载、增量跟随与下载。终端颜色码处理后安全显示，不渲染日志中的HTML或执行日志命令。

### 复测语义

- `failed`：默认FAIL/CRASH/TIMEOUT/XPASS/INCOMPLETE；界面显示实际选择数量，XFAIL/SKIP默认不选但可明确选择。
- `selected`：当前勾选配置；`all`：冻结完整集合。
- 冻结原SDK、环境revision、源码、集合、参数、seed、插件与设备类型要求；不得在复测时偷偷切latest。
- 复测生成新任务、记录requested_by、rerun_of、source_daily_batch、selected_set_digest和attempt。原报告保持不变。
- 结果展示FAIL→PASS、仍失败、新增失败、未覆盖；局部复测未运行的配置不计为已恢复。
- 环境丢失：按原manifest重建后校验；制品不可得返回明确错误。设备不可用等待或失败，不静默降级为CPU。
- 系统Daily属于system；用户点击公共报告复测得到个人workspace任务。通过显式 `source_daily_batch_id` 引用公共批次，不把私有tasks.parent跨workspace硬连，避免违反现有组合外键和归属规则。

## 7. 数据库与日志索引

**日志内容本身入数据库，数据库不只是记录文件路径。** HTML、Trace、大附件继续走现有证据存储索引；日志不依赖扫描本机目录查询。

| 数据表 / 扩展 | 主要内容 |
|---|---|
| daily_definition_revisions | 不可变计划配方、来源选择器、suite、时区/时间、deadline、门禁、设备要求 |
| daily_occurrences | 业务日期、slot、revision、调度期望与实际触发，唯一约束防重复/补跑冲突 |
| daily_batches / daily_attempts | 来源、SDK、环境、源码、collection、触发者、状态、最终质量、rerun lineage |
| pipeline_steps / step_attempts | 逐阶段状态、计时、重试号、worker、错误、输入/输出digest、租约generation |
| environment_revisions / environment_probes | SDK组件与包哈希、Python/recipe身份、设备要求、探针结果 |
| suite_revisions / collection_items | 固定选择表达式与实际参数化配置集合 |
| daily_run_links | batch/attempt与现有pytest任务、分片、角色、required标记的关联 |
| case_results / case_stage_results | 扩展configuration_id、规范化status、参数维度、失败指纹、pipeline关联 |
| daily_report_revisions | 每次已发布的质量汇总、metrics_version、policy_revision、数据水位 |
| daily_calendar_entries | definition/date/维度的投影、publication_id、strict质量、原因和复测徽标 |
| task_log_chunks | 日志原文、顺序、水位、哈希、时间范围、任务/步骤/worker/配置归属 |
| task_log_events | 可筛选事件、结构字段、level、简短消息、对应chunk与偏移 |
| log_ingest_receipts | producer/sequence/attempt去重、最后持久水位、丢弃/限额状态 |
| exports / audit_events | 异步导出、正式发布变更、取消/复测/配置变更审计 |

### 日志写入

- stdout/stderr、pytest捕获、`triton_dev_log`和流水线结构事件统一通过collector写库。
- 按producer有序seq批量入库（目标约0.5–1秒或64KiB一块，实施时压测）；不能逐字符写SQL，也不能结束后一次性塞巨型JSON。
- producer = step_attempt + process/worker + stream；唯一键 `(producer_id, seq)` 支持断线重传去重。chunk包含content_sha256与首尾事件时间。
- 结构化case日志保存configuration_id、nodeid、phase、worker、pid；原始进程流保持原本归属。不能把捕获输出和实时输出重复归算成两次事件。
- collector短暂故障可使用有界磁盘spool作为传输缓冲；主查询与最终报告仍以DB持久数据为准，不能声称本地缓冲已经归档成功。
- 完成报告前检查终态事件、预期case结果、日志flush水位并发布report_revision；不足时标记 `evidence_incomplete`，不能严格全绿。
- 凭据在采集前脱敏；连接字符串/环境变量按允许字段收集。界面按日志等级折叠，不丢掉错误上下文。
- 配额明确记录 `truncated`、丢弃区间与保留策略；禁止静默截断后宣称“完整日志”。磁盘/数据库耗尽为可见基础设施失败。

### 查询、分区与保留

PostgreSQL按日志采集月份或业务日期范围分区（依据实际量选择一种），跨分区唯一性包含分区键；查询尽量先给时间/任务范围。

必需索引：`(workspace_id, task_id, producer_id, seq)`、`(batch_id, step_id, created_at, id)`、`(run_id, configuration_id, phase, created_at, id)`、`(run_id, worker_id, created_at, id)`。结果表增加常用 `(batch_id,status)` / `(batch_id,operator,status)` / duration排序索引，参数热字段类型化，不把全部过滤写成大JSON扫描。

日志事件关键词可用PostgreSQL全文索引；中文任意子串搜索需要明确实现ILIKE + 可选pg_trgm，不能把默认英文分词视为中文检索。优先限制batch/time后搜索、游标分页；不提供任意SQL和无限范围正则。

日志按producer seq定位，跨producer时间相同用稳定游标排序；不能声称不同机器的wall-clock有严格全局顺序。日志下载支持原始stream与结构化JSONL。SQLite只做本地功能验收，分区/并发/查询性能在PostgreSQL单独验收。

建议可配置保留：质量汇总与谱系长期；case明细180天；完整日志90天、失败日志180天。归档/删除动作可审计，过期日志显示“已归档/已过期”，不显示为空白。具体容量与时间由部署数据量确认，不预设无限存储。

## 8. API与CLI一一对应（拟议）

统一业务服务 `DailyService / PipelineService / ReportService / LogService`。HTTP做权限/验证，`triton-dev daily ...` 默认作为同一Server的客户端；普通用户CLI不绕过API直接读写数据库。离线 `platform manage` 仅负责受控管理与迁移。

| HTTP | CLI（前缀 `triton-dev`） |
|---|---|
| POST /api/daily/v1/definitions | daily definition create --file plan.json |
| GET /api/daily/v1/definitions | daily definition list |
| GET /api/daily/v1/definitions/:id | daily definition show ID |
| POST /api/daily/v1/definitions/:id/revisions | daily definition revise ID --file plan.json |
| POST /api/daily/v1/definitions/:id/state | daily definition set-state ID --state enabled或disabled |
| POST /api/daily/v1/batches | daily trigger --definition ID --date DATE --idempotency-key KEY |
| GET /api/daily/v1/batches | daily list --definition ID --from DATE --to DATE |
| GET /api/daily/v1/batches/:id | daily status BATCH |
| GET /api/daily/v1/batches/:id/events | daily events BATCH --after CURSOR --follow |
| POST /api/daily/v1/batches/:id/cancel | daily cancel BATCH |
| POST /api/daily/v1/batches/:id/resume | daily resume BATCH --from-step STEP |
| POST /api/daily/v1/batches/:id/reruns | daily rerun BATCH --scope failed或all或selected --selection-file nodes.json |
| GET /api/daily/v1/calendar | daily calendar --definition ID --month YYYY-MM |
| GET /api/daily/v1/batches/:id/report | daily report BATCH --format json |
| GET /api/daily/v1/batches/:id/cases | daily cases BATCH --status FAIL,XFAIL --operator matmul --search TEXT --cursor CURSOR |
| GET /api/daily/v1/batches/:id/cases/:configuration_id | daily case show BATCH --configuration ID |
| GET /api/daily/v1/logs | daily logs BATCH --configuration ID --worker gw1 --phase call --search TEXT --after CURSOR |
| GET /api/daily/v1/logs/stream | daily logs BATCH --follow --format jsonl |
| POST /api/daily/v1/batches/:id/exports | daily export BATCH --format html或csv或json --scope all或filtered |
| GET /api/daily/v1/exports/:id | daily export status EXPORT |
| GET /api/daily/v1/exports/:id/download | daily export download EXPORT --output PATH |
| POST /api/daily/v1/batches/:id/publications | daily publish BATCH --attempt ATTEMPT --reason TEXT |

传入definition/source/节点集合等使用ID与有界schema；不接收自由shell、可执行路径或任意下载URL。file导入的command/marker遵循注册配方允许范围。

### Agent契约

- 每条命令支持 `--json --non-interactive`、稳定command ID与 `describe` schema；输出沿用现有envelope。
- 认证从受限profile/会话凭据引用读取，不把Key/密码放命令行或回传JSON。姓名登录可复用但不能借名字获取管理权限；管理来源、计划和正式发布需单独服务器能力授权。
- 普通触发立即返回202 / task_id；不让模型等待长HTTP请求。`--wait --timeout` 是客户端轮询任务，超时返回已有ID且不自动取消服务任务。
- Agent不负责日常定时触发或绿红判定。模型可读取证据、触发登记任务和生成解释；确定性控制器和版本化规则计算质量。
- 所有写操作有幂等键与输入digest；同键不同输入409，同键重试返回同一对象；游标和结果快照可续读。
- 普通提交返回成功只表示任务创建；`--wait` 的退出码区分质量绿/红、仍执行或客户端等待超时、鉴权/参数/服务错误，具体固定映射在实现时同步describe。
- JSONL跟随输出区分日志事件与进度，诊断只写stderr，不混入JSON正文。建议支持请求ID、summary与`next_action`字段。
- 公共Daily报告可读，个人复测日志按workspace私有；所有CLI/API沿用同一对象归属检查。

## 9. 调度、恢复与可追溯性

- 多进程scheduler用数据库锁/唯一occurrence认领；重启后按misfire策略补跑。默认只补有限窗口，避免补跑一个月压满设备。
- 没有新SDK时等待到deadline；每日watchdog记录漏触发、构建超时、设备饥饿、collector中断。日历不会因为后台没启动而一直空白。
- 依赖阶段先持久化输出再推进；租约携带generation，过期worker禁止回写/发布。可能仍存活的旧进程必须先reconcile，不能盲目重新执行板卡任务。
- 网络拉取/临时下载可有限重试；哈希或源码漂移为确定性错误，不重复撞运气。case自动重试不把首个失败覆盖；波动标记FLAKY与全部观测并存。
- 每个报告可追到：计划revision → occurrence → batch/attempt → SDK清单 → 环境receipt/探针 → 源码 → collection → run/configuration → 阶段 → worker/process → 日志游标和证据hash。
- 报告固定`data_watermark + report_revision`，实时运行标注provisional；终态汇总、日历投影与正式publication在一致事务/可重放outbox下更新，不能图表绿而表格仍有红。
- SDK改变后可从报告发起已实现的regression调查，但不能把任意Daily失败自动认定为外部组件责任。

## 10. 配方示例（拟议schema）

```json
{
  "name": "tx82-main",
  "schedule": {"timezone": "Asia/Shanghai", "hour": 8, "minute": 0, "sdk_deadline": "10:00", "finish_deadline": "16:00"},
  "sdk_selector": {"source_id": "registered-sdk-source", "channel": "daily", "platform": "linux-x86_64", "require_new_build": true},
  "environment_recipe_id": "registered-cp310-device-recipe",
  "suite_revision_id": "tx82-smoke-v1",
  "execution": {"workers": 4, "resource_class": "tx82-board", "timeout_seconds": 7200},
  "quality_policy": {"calendar_mode": "strict_all_pass", "require_nonempty_collection": true, "require_complete_evidence": true}
}
```

此处ID引用预登记对象，示例不能直接在现有CLI使用；真实板卡/制品探针须由部署环境提供，mock演示单独channel，不能混入正式质量日历。

## 11. 实施顺序与验收

1. **持久流水线与CLI**：新revision/occurrence/steps模型、来源选择、环境resolver、SQL调度，先用mock制品+真实CPU pytest打通。
2. **数据库日志与报告契约**：collector、归属与索引、完整性水位、结果分类/统计、筛选/复测、API/CLI契约测试。
3. **简约日历与报告UI**：左侧Daily入口，月历→日期/构建/attempt→质量总览→可筛选表格→case日志；复用现有设计tokens和结果块，不增加大面积装饰图。
4. **真实SDK/板卡验收**：上游凭据与manifest、构建环境与探针、设备租约/驱动、容量压测和日志保留策略。不能用mock全部通过替代该阶段。

必验边界：XFAIL/XPASS/SKIP与pytest退出码0；空collection；收集失败；缺日志/未知结果；构建失败但已有旧latest；同日多构建；晚到SDK；跨午夜；漏调度/重启；重复触发；部分复测不得刷绿；官方重跑发布审计；旧worker fencing；并发日志乱序/断线重传/限额；跨workspace访问；中文关键词；大结果集分页；所有公开API都有CLI；390px与桌面日历/表格可用。

本次仅新增设计文档与进度记录，未开启真实制品拉取、创建计划或改变现有任务。
