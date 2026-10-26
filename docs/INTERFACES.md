# CLI、AI 与错误协议

```bash
triton-dev --help
triton-dev env export --help
triton-dev describe env.prepare --json --non-interactive
triton-dev capabilities --json --non-interactive
triton-dev candidates env.sdk --json --non-interactive
triton-dev candidates env.component --json --non-interactive
```

describe 的参数、默认值与帮助来自真实 argparse parser。现增加 input_schema（解析后参数对象）与 output_schema（版本化 envelope）；command-specific data 仍允许开放结构，不宣称每个结果体都有完整 Schema。env export 的 sh 模式仍为文本例外。capabilities 同时标注 implemented/unsupported，agent.regression 等占位不能当成可执行功能。

新增接口、示例和边界见 [OFFLINE.md](OFFLINE.md)。

## 参数与交互

`--python` 解析可执行路径或 PATH 名称，保留 venv 软链接路径；prepare 通过选定解释器的 `-I -m venv` 创建环境，安装前核对版本和平台。准备协议 v3 使用新缓存标识，不复用旧版准备结果。失败状态包括 PYTHON_UNAVAILABLE、VENV_CREATION_FAILED、PYTHON_IDENTITY_MISMATCH。这里的身份校验不证明 ABI 或设备功能兼容。

SDK 完整名称、YYYYMMDD、本地 latest 支持同一服务解析。download 日期支持 YYYYMMDD/分钟精确格式，远端 latest 与本地 latest 分开。显式参数不被交互覆盖；-i 与 --non-interactive 互斥。缺必需候选时返回 NEEDS_INPUT，非终端不弹菜单。当前交互仅编号选择，搜索式候选是 TODO。

## 输出

普通命令默认结构化输出；--json 显式表示机器调用意图。后续可新增人类表格，但 JSON 协议不能改变。

```json
{"schema_version":1,"status":"ok","data":{},"error":null,"evidence":[]}
```

工具错误返回非零退出码和 error.code/message/details。env exec / run 返回真实子命令退出码，data.outcome=failed 不能因 status=ok 而被调用方忽略。diagnose 成功完成一次“不复现”的调查仍可退出 0，结论看 data.conclusion，不将其等同 case 通过。

env export --format sh 是例外：成功只输出代码，失败返回非零且不会输出半段有效 shell；调用者必须检查退出码再 eval。JSON 导出数据含 variables/unset。默认只导出相关变量；--all 必须显式指定，可能包含凭据。

```bash
env_script="$(triton-dev env export --current --format sh --non-interactive)" || exit 1
eval "$env_script"
python -m pytest tests/smoke
```

## v0.1 离线 AI 问答

```json
[
  {"schema_version":1,"task_id":"scripted-task","turn_id":1,"type":"query","action_id":"env.sdk.list","args":{}},
  {"schema_version":1,"task_id":"scripted-task","turn_id":2,"type":"finish","conclusion":"insufficient_evidence","evidence_ids":["sdk-list-1"]}
]
```

显式保存为临时输入后运行 `triton-dev agent scripted responses.json`。这不是用户日常配置，是协议回放输入。也可以直接在 Python tests 注入 ScriptedModel，无需文件。

控制器只允许 env.sdk.list，CLI Bridge 不接受自由 shell；证据 ID 必须由代码实际观察产生；finish 不能把 list 查询变成归因结论。ask_user 返回 needs_input，不自动获取“同意”。模型 API 与实验动作留待 TODO 接入。

## 主要错误

SDK_NOT_FOUND、SDK_INCOMPLETE、INVALID_DATE、WHEEL_SELECTION_FAILED、ENV_NOT_PREPARED、INCOMPLETE_ENVIRONMENT、INSTALL_FAILED、SOURCE_CHANGED、REMOTE_LIST_UNSUPPORTED、CHECKSUM_MISMATCH、UNSAFE_ARCHIVE、UNSUPPORTED、NEEDS_INPUT、TIMEOUT、COLLECTION_FAILED、MODEL_PROTOCOL_ERROR、UNKNOWN_EVIDENCE、ACTION_NOT_ALLOWED、FINISH_REJECTED。

完整错误枚举/版本协商和生成式接口参考文档是后续任务；当前协议由代码和测试共同看护。

## pytest 服务 HTTP 接口

所有任务接口沿用 Bearer、Host/Origin 校验。完整配置见 [pytest 服务](PYTEST_SERVER.md)。

| 方法 / 路径 | 请求 / 响应 |
| --- | --- |
| GET /api/jobs | 返回 job_id、kind、默认隔离、max_workers、扩展 schema；kind=pytest 支持以下流程 |
| POST /api/tasks | {job_id,idempotency_key}；pytest 项目创建异步 collection，普通任务照常执行 |
| GET /api/tasks / GET /api/tasks/:id | 返回真实阶段、汇总、收集结果、快照、附件和复测对照 |
| GET /api/pytest/extensions | 服务器登记的扩展 schema/default/version |
| POST /api/pytest/runs | 必需 {collection_id,nodeids,isolation,idempotency_key}，可选 workers（默认1）、extensions；isolation=case/session/xdist，只允许成功收集中的唯一 nodeid |
| POST /api/tasks/:id/rerun | {mode:failed或all,idempotency_key}；新记录保留 parent |
| POST /api/tasks/:id/cancel | {}；取消运行及其当前 case 进程组 |
| GET /api/tasks/:id/artifacts/:artifact_id | 鉴权后下载显式附件，10 MiB 上限、无自由路径 |
| GET /api/tasks/:id/events?after=N | 有限批次 SSE 状态事件；阶段数据通过任务详情刷新 |

幂等键必须对应相同 job、选择、隔离与 parent，workers 和规范化扩展配置也参与比较；变更请求复用键返回 IDEMPOTENCY_CONFLICT。collection/run 数据 schema_version 仍为1，字段为向后兼容新增。

## Profiling demo HTTP

新增鉴权GET /api/profiling/catalog、POST/GET /api/profiling/reports、GET /api/profiling/reports/:id 与 /trace。仅mock适配器，state=generated、correctness=not_checked，完整严格请求字段和边界见[Profiling](PROFILING.md)。

pytest collection元数据新增可选operator字段，使用pytest.mark.operator(name)显式标注；已有HTTP路径和运行请求不变。批次统计由页面根据原始test_results、收集元数据和父记录推导，统计导出schema_version=1；口径见[批次统计](RUN_STATISTICS.md)。

逐配置测试报告由现有collection、test_results和原始test_started/worker_exit事件生成，不修改HTTP协议或原始outcome。展示分类、时间与导出字段见[测试报告](TEST_REPORT.md)。
