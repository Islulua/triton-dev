# Daily 首版使用说明

2026-10-27。已实现 `/api/daily/v1`、`triton-dev daily` 和 `/#daily` 页面。完整目标见 [DAILY_PIPELINE_DESIGN.md](DAILY_PIPELINE_DESIGN.md)，本文件是实际交付范围。

## 当前可用

- 月历：严格全PASS绿色，其余终态红色；排队/执行蓝色、未运行灰色。点击日期进入报告。
- 公共历史是明确标注的数据库生成样例，未执行pytest；手动或每日调度触发则运行真实CPU pytest。SDK发现、环境准备仍为mock，不下载/安装真实SDK，不访问板卡或模型。
- 可创建个人计划，选择内置CPU算子pytest集合（matmul/softmax/reduce/transpose，各8个shape）、Workers 1..8、上海时区每日时间与启用状态。
- 场景：all_pass、mixed、xfail_only、build_failure。真实运行的mixed场景产生28 PASS、1 FAIL、1 SKIP、1 XFAIL、1 XPASS。
- 五步流程：SDK发现、模拟环境准备、真实用例收集、pytest/xdist执行、报告归档。输入冻结在任务spec，保留SDK digest、环境revision、Python版本、源码digest、collection digest、nodeids和计划revision。
- 报告：严格PASS比例、测试通过率、执行覆盖率、配置数、测试/流水线时间、P50/P95、累计阶段工时、算子结果与各结果类别。
- 完整逐配置表可按结果多选、算子、dtype、文件、worker、失败阶段、耗时范围、nodeid/参数搜索；游标分页；查看参数、起止时间和原始阶段。
- 配置日志直接跳到页面下方日志区域；支持配置/worker/阶段/关键词查询与分页。原始进程输出、阶段证据与worker日志内容都存入数据库，不依赖扫描日志目录查询。
- 一键失败项复测、勾选复测、原任务完整重跑；复测固定输入，保留source_daily_batch_id。公共报告复测归个人空间，不把个人任务公开。
- 导出完整或当前筛选HTML/CSV/JSON，离线HTML保留结果色块，CSV做字段转义和公式前缀保护。
- 沿用SQL持久队列、心跳、generation fencing、幂等键、取消与中断识别。中断后使用显式完整重跑，当前不提供Daily阶段resume。

## 界面

预览：[质量日历](../frontend/design/daily/calendar.png)、[复测报告](../frontend/design/daily/report-rerun.png)、[手机布局](../frontend/design/daily/calendar-mobile.png)。

左侧“Daily” → 选择计划/月 → 日期格 → 当天报告 → 配置表 → case日志/复测。

公共Mock计划默认不启用自动执行。点击“新建计划”，选择CPU算子套件、设置时间和Workers并勾选启用，服务运行期间每30秒检查并按计划触发当天任务。每计划/业务日期使用稳定幂等键；计划修改不自动重跑当天，需手动触发。首次无数据时可点击“加载演示日历”，幂等生成本月过去日期的公共mock历史。

日历保留首个正式结果；部分复测不能刷绿。公共日期优先公共记录，个人补跑与复测不覆盖它。若为个人计划，首个全范围任务为该日日历结果。尚未提供“更换官方publication”入口。

## CLI与认证

CLI与网页调用同一Server，不能绕过workspace检查直接改数据库。使用server可选依赖，原始Bearer服务不提供Daily v1端点：

```bash
python -m pip install -e '.[server]'
# PostgreSQL与serve --multi-user启动方式见PLATFORM_USAGE.md
triton-dev daily login --name '你的登录名' --server http://127.0.0.1:8765 --json
triton-dev daily demo --json
triton-dev daily plan list --json
```

登录会话保存在本机0600文件，默认 `~/.cache/triton-dev/daily-session.json`；可用 `--session-file PATH` 切换。会话与server origin绑定，禁止转发重定向；输出不包含会话token或CSRF。姓名登录不验证身份，适用于当前可信内网协作模式。

个人计划示例 `daily-plan.json`：

```json
{"name":"我的CPU Daily","scenario":"mixed","operators":["matmul","softmax"],"workers":4,"hour":8,"minute":0,"enabled":true}
```

```bash
triton-dev daily plan create --file daily-plan.json --json
triton-dev daily plan update PLAN_ID --file daily-plan.json --json
triton-dev daily trigger --plan PLAN_ID --date 2026-10-27 --idempotency-key my-daily-20261027 --wait --timeout 300 --json
triton-dev daily calendar --plan PLAN_ID --month 2026-10 --json
triton-dev daily list --plan PLAN_ID --month 2026-10 --json
triton-dev daily status BATCH_ID --json
triton-dev daily report BATCH_ID --json
triton-dev daily events BATCH_ID --after 0 --json
triton-dev daily cases BATCH_ID --status FAIL,XPASS --operator matmul --json
triton-dev daily logs BATCH_ID --configuration-id CONFIG_ID --worker gw0 --search MOCK --after 0 --json
triton-dev daily rerun BATCH_ID --scope failed --idempotency-key retry-001 --json
triton-dev daily rerun BATCH_ID --scope selected --selection-file nodes.json --idempotency-key retry-002 --json
triton-dev daily cancel BATCH_ID --json
triton-dev daily export BATCH_ID --format html --output daily-report.html --json
```

`nodes.json` 为原任务实际nodeid的非空JSON数组。scope=all指原任务的全部配置；如果原任务本身是子集，仍然只是该子集，不能解释成完整Daily覆盖。

所有命令支持 `--json --non-interactive` 与 `describe daily.trigger` 等schema查询。提交成功仅代表创建任务；`trigger --wait` 退出0表示严格全绿、1为终态非全绿、3为客户端等待超时（不自动取消），参数/认证/服务错误沿用退出2。对不同日期或输入使用不同幂等键，同键不同输入返回冲突。

日志支持after游标增量查询，客户端Agent可轮询；当前尚无SSE/JSONL持续流。导出在固定32配置上同步完成，不是假装有大规模异步导出任务。

## API / CLI 对应

| API，前缀 `/api/daily/v1` | CLI，前缀 `triton-dev daily` |
|---|---|
| GET /definitions | plan list |
| POST /definitions | plan create --file |
| PATCH /definitions/:id | plan update ID --file |
| POST /demo | demo |
| GET /calendar | calendar --plan --month |
| GET /batches | list --plan --month |
| POST /batches | trigger --plan --date --idempotency-key |
| GET /batches/:id | status ID |
| GET /batches/:id/report | report ID |
| GET /batches/:id/events | events ID --after |
| GET /batches/:id/cases | cases ID，支持表格各筛选项 |
| GET /batches/:id/logs | logs ID，支持配置/worker/阶段/步骤/等级/搜索/after |
| POST /batches/:id/cancel | cancel ID |
| POST /batches/:id/reruns | rerun ID --scope --selection-file --idempotency-key |
| GET /batches/:id/export | export ID --format --output，支持同一组筛选 |

会话登录复用POST /api/sessions，CLI为daily login。写请求复用Cookie/CSRF与同源策略；后台只运行打包在工具内的可信CPU fixture，不接受任意命令/路径。

## 数据库与追溯

迁移 `0003_daily` 增加daily_plans、daily_case_results、daily_log_chunks。Daily使用现有tasks/task_events/SQL队列。计划配置修改产生新revision，旧任务保留完整spec。case表保留规范化结果与原始阶段；日志表保存内容、seq、时间、步骤、configuration_id、worker、phase、stream、level、sha256，按任务/case和任务/步骤/worker建立索引。

日志每个任务最多10000个有界chunk，超过上限显式报错，不静默截断后标绿。worker磁盘日志达到上限同样使报告失败。原始SQL日志是查询事实源，执行目录是采集暂存及证据。source/interpreter与冻结输入不一致时拒绝悄悄使用新版本执行。

当前日志检索是任务范围内的数据库子串查询；大规模分区、全文/中文检索、保留/归档worker、使用量配额和监控告警尚未接入，不宣称已完成设计稿全部生产能力。

## 当前明确边界

真实上游制品、原生环境Builder/探针、任意登记项目suite adapter、设备租约与容器、漏调度补跑/deadline watchdog、正式结果发布替换、大导出任务尚未接通。当前定时器只调度当天到点的启用计划，不自动补历史，服务需持续运行；过期租约进入interrupted并由显式重跑恢复。

Mock历史的红绿仅说明演示数据，CPU任务结果仅说明测试框架逻辑；不证明SDK或板卡质量。上面未实现项保留在设计文档，不通过填充假成功掩盖。

报告定位链接保留 `daily_batch`，case日志链接再加 `daily_case`；刷新或复制链接可恢复对象，访问仍执行同一workspace授权检查。
