# 离线自动化操作手册

本轮功能使用真实本地子进程、pytest、venv/pip 和 HTTP 服务验证。合成 SDK、脚本模型、脚本历史评估器只模拟外部输入；不能证明真实 LLVM/cmodel/Torch/Triton 的兼容性。

## 环境与组合

```bash
triton-dev env preflight --sdk SDK --python /path/to/python
triton-dev env save baseline --sdk SDK
triton-dev env save trial --sdk SDK --triton-sdk OTHER_SDK
triton-dev env saved list
triton-dev env saved show baseline
triton-dev env saved diff baseline trial
triton-dev env prepare --saved baseline
triton-dev env exec --saved baseline -- python -c 'import triton; print(triton.__file__)'
```

名字不可覆盖。`save` 冻结日期/latest 到具体目录，记录完整 SDK 文件清单哈希、选中 wheel 和解释器身份。恢复前核对源内容；文件删除、添加或改变均返回 SOURCE_CHANGED。未复制 SDK 二进制，源目录必须保留。`saved show/diff` 只查看历史记录，不宣称当前源文件有效。

`--saved` 不能同时指定 SDK、组件覆盖或 native-only。恢复使用记录中的解释器。Python wheel 覆盖是已支持的 mix；原生共享 lib 归属尚未确认，cmodel 混用仍 UNSUPPORTED。

管理器新增轻量运行依赖 `packaging>=24`。目标解释器以隔离模式加载管理器的纯 Python packaging 库，生成自身支持的 wheel tags 和 marker 环境。预检检查选中包的 Requires-Python、基础 Requires-Dist、版本约束和 markers；缺失的依赖、extras 或直接 URL 保持 unknown，由离线 pip 安装进一步解析。它不是完整依赖求解器，也不证明原生 ABI。

## 持久运行、pytest 阶段与复测

```bash
triton-dev runs start --cwd /project --pytest -- tests/test_kernel.py
triton-dev runs start --saved baseline --cwd /project -- python reproduce.py
triton-dev runs list
triton-dev runs show RUN_ID
triton-dev runs rerun RUN_ID --failed
triton-dev runs diff ORIGINAL_RUN NEW_RUN
triton-dev cases show /project 'tests/test_kernel.py::test_add[fp16]'
triton-dev cases lint /project --require-id
```

只有 `runs` 和 task/agent 工作流显式保存运行数据；原有 `env exec` 不默认写报告。记录位于 `CACHE/runs/run_UUID`，包含 request、result、阶段事件、stdout/stderr 和独立 cache/tmp。同一次运行不会被复测覆盖。

`--pytest` 接受目标路径/nodeid，不接受任意 pytest 选项；项目配置控制选项。目标解释器需自行具备 pytest，工具不会隐式安装。插件采集 setup/call/teardown，worker 分文件写入后聚合；这些是 pytest 阶段，不是 kernel 编译/launch 阶段。收集失败、崩溃和超时可能没有失败 nodeid，`--failed` 会明确报 NO_FAILED_CASES。

复测沿用解释器、cwd、环境描述和目标，但读取当前源码/配置，不恢复历史源码和输入。`runs diff` 展示请求及阶段结果差异，不证明测试条件完全一致。

进程执行持续排空两路输出；内存保留每路最后 1 MiB，持久日志保留每路前 8 MiB。字节数和截断状态均明确记录。超时/取消终止进程组；已脱离进程组的恶意进程不在此隔离模型内。记录目录是本地受信任数据，可能包含原始敏感日志。

## 故障判据与历史搜索

predicate.json 示例（选择其中一种）：

```json
{"kind":"text","match":"TARGET_FAILURE"}
```

```json
{"kind":"exit","exit_code":7}
```

```json
{"kind":"stage","phase":"call","match":"AssertionError"}
```

```json
{"kind":"numerical","phase":"execute","atol":0.001,"rtol":0.01}
```

数值判据读取命令 stdout 的完整 JSON，或 Python 接口 result.structured：

```json
{"phase":"execute","actual":[1.2,2.0],"expected":[1.0,2.0]}
```

当前只支持非空、等长、有限数值的一维数组；NaN/Inf、缺失字段、日志混入 JSON 等返回 insufficient_evidence。数值超限即目标故障，不要求进程非零；原始运行退出码保持不变。

```bash
triton-dev diagnose classify RUN_ID --predicate predicate.json
triton-dev diagnose history --versions SDK_OLD SDK_MID SDK_NEW \
  --predicate predicate.json --repeat 2 --budget 20 --native-only -- python reproduce.py
```

history 按用户显式的从旧到新顺序穷举，预算单位为执行次数，不假定故障单调。先解析所有 SDK 名称，实验期间不重解析 latest。只在全部版本稳定可判、首个基线通过时给 first_failure。否则保留 first_observed_failure 并返回 insufficient_evidence。回归后恢复、偶现、缺版本和不同故障都不被当成二分搜索的确定答案。

`--native-only` 只提供原生路径，不代表验证 SDK Python 包或实际原生加载；不加此参数则要求环境事先 prepare。`ScriptedEvaluator` 是显式 mock 接口，结果带 source=mock。

## 证据导出

```bash
triton-dev runs export RUN_ID --output evidence.zip --redact-env MY_SECRET_VALUE
triton-dev runs verify-export evidence.zip
```

只导出终止运行的 record、日志和事件，含版本化 manifest 和脱敏后 SHA-256。默认不导出整个继承环境、SDK、缓存或 tensor 数据。自动识别部分 token/password/Bearer 格式，已知秘密应通过环境变量名字显式传递；自动脱敏不保证识别所有秘密。导出不覆盖已有文件，默认最大 32 MiB。校验器检查清单、重复/越界路径、大小及哈希，不解压执行；完整性不等于来源认证。

## 离线 agent 与恢复

```bash
triton-dev agent workflow workflow.json --checkpoint state.json --max-experiments 6
```

workflow.json：

```json
{
  "predicate":{"kind":"text","match":"TARGET"},
  "recipes":{
    "g1":{"role":"good","request":{"argv":["python","-c","pass"],"cwd":"/absolute/project","timeout":10}}
  },
  "responses":[
    {"action":"experiment","recipe_id":"g1"},
    {"action":"finish","conclusion":"insufficient_evidence","evidence_ids":["g1"]}
  ]
}
```

recipes 是操作者提供的受信任配置。模型只选 recipe_id；自由 argv、未知动作、伪造证据和无依据结论被拒绝。当前 provider 为 ScriptedModel，不调用模型 API。change_associated 需要至少两次 good 通过和两次 bad 目标故障，且引用全部观察；最终缺陷归属仍未知。

checkpoint 保存累计轮数、实验次数、耗时和 pending run。恢复禁止改变 recipe/predicate，未完成副作用不会自动重做。恢复时新 responses 从当前步骤开始提供，不重新提交已完成的 recipe。预算耗尽状态可由用户显式增加预算继续。脚本模型调用是本地即时操作；实际网络 provider 的超时/费用控制留待真实接入。

仓库 `skills/triton-dev-env` 和 `skills/triton-dev-triage` 可供外部编码 agent 使用；未自动安装到个人 skill 目录。

## 本地任务服务

不传 --jobs 时保留原来的只读 capabilities 服务。启用任务时：

```bash
# TOKEN 由自己的环境配置注入，至少 16 字符，不写进 jobs.json
triton-dev serve --jobs jobs.json --token-env TRITON_DEV_SERVER_TOKEN --port 8765
```

jobs.json 是受信任本地任务登记表：

```json
{"smoke":{"argv":["python","-m","pytest","tests/smoke"],"cwd":"/absolute/project","timeout":60}}
```

若使用裸 python，任务默认绑定管理器解释器；可以显式填 python 可执行路径，或 request.environment 配置已准备的环境。task 请求不能改变 argv/cwd/环境。

- `GET /api/capabilities`：公开只读能力。
- `GET /api/jobs`、`GET /api/tasks`、`GET /api/tasks/ID`：Bearer 鉴权。
- `POST /api/tasks`：`{"job_id":"smoke","idempotency_key":"unique-request"}`。
- `POST /api/tasks/ID/cancel`：`{}`。
- `GET /api/tasks/ID/events`：有限批次 SSE；Last-Event-ID 或 ?after=N 续读。

只绑定 127.0.0.1。任务接口检查 Host、仅允许匹配当前 Host 的同源 Origin 或非浏览器请求，拒绝跨源访问、不返回 CORS 允许头。当前用于本地客户端及同源网页前端，无多人权限或远程部署承诺。一个目录只允许一个 task service，单 worker 串行调度，避免共享设备并发；没有硬件资源探测。任务状态与幂等索引写入 CACHE/tasks；重启将 queued/running 标记 interrupted，不自动重跑；正常关闭取消队列和执行进程。服务被 SIGKILL 后不保证清理遗留进程，重启只标记 interrupted，不自动重试。SSE 是状态事件，不是完整实时日志流。

## 可复现实例

```bash
python examples/offline_demo.py --workdir /new/isolated/demo-directory
```

脚本要求目标目录不存在，创建明确标记的合成 SDK、离线安装、组合保存、真实 good/bad 子进程、pytest 阶段失败、历史搜索、脚本模型工作流和证据包；不使用私网、真实设备或 AI API。演示失败是预期行为，脚本以自动断言确认分类。

网页前端可通过 `serve --ui frontend/dist/client` 同源加载；前端默认是明确标记的演示模式，设置中接入登记任务 API。环境、用例与诊断尚无 HTTP 接口，见 frontend/README.md。
