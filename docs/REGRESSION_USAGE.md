# 回归定位工具：当前可运行范围

2026-10-26：已实现CLI、持久状态机、后台HTTP任务和网页。SDK清单/update、组件版本和模型是mock接口；实验执行真实CPU pytest，不验证板卡、真实wheel/so替换或真实模型API。当前不能把任意实际pytest命令传给网页并声称SDK归因。

## 开始

在安装了本项目与pytest的Python环境中：

```bash
triton-dev agent regression catalog
triton-dev agent regression start --cache-root /path/to/cache
triton-dev agent regression start --config regression.json --cache-root /path/to/cache
triton-dev agent regression status reg_<id> --cache-root /path/to/cache
triton-dev agent regression report reg_<id> --format md --cache-root /path/to/cache
triton-dev agent regression resume reg_<id> --cache-root /path/to/cache
triton-dev agent regression cancel reg_<id> --cache-root /path/to/cache
triton-dev agent regression replay reg_<id> --experiment exp_0003 --cache-root /path/to/cache
```

CLI start/resume同步执行；server异步排队。report以统一JSON envelope返回，md/html内容在data.content。任务在cache/regressions/<task-id>；服务端cache为TaskManager实际任务根目录，网页报告的重放命令已使用该目录。start无需config时使用默认场景与预算。

配置示例：

```json
{
  "adapter": "mock",
  "scenario": "component",
  "baseline": "mock-sdk-20261010",
  "search_mode": "earliest_verified",
  "repeats": 2,
  "max_experiments": 60,
  "max_seconds": 600,
  "max_model_calls": 12,
  "model_profile": {"provider": "mock", "model": "mock-planner-v1"}
}
```

场景：component、interaction、no_regression、bad_baseline、nonmonotonic、unavailable、flaky。mock清单为2026-10-10至19。单组件从15日失败，交互依赖LLVM+cmodel；非单调场景13日失败、14/15日恢复、16日起失败，严格模式须找到13日。缺失场景14日产生不可用证据，不把skip算通过。flaky需要至少2次重复才能观察分歧。

工作流顺序：baseline重复通过→mock update锁定latest→latest重复验证→目标失败才二分→严格模式补扫→边界独立重复→模型排序合法候选→双向组件替换→报告。模型只返回candidate_id和已有evidence_id，不接收执行工具。当前模型配置只允许mock；真实API参数明确返回UNSUPPORTED，不索取凭据或隐式联网。

## 网页与HTTP

启动既有serve并登记jobs（空对象也可）即可启用；回归任务与pytest任务分别排队。访问 /#regression，连接服务令牌后选择场景、baseline、搜索精度、重复数和预算。页面展示进度/实验数量/模型调用、版本轨迹、组件矩阵、阶段与模型决策、原始pytest日志、报告和JSON/Markdown/HTML导出。取消、恢复均保留任务账本。

新增接口沿用Host/Origin/Bearer验证：

- GET /api/regression/catalog
- GET /api/regression/tasks（最近50条）
- POST /api/regression/tasks：`{"config": {...}, "idempotency_key": "unique-key"}`
- GET /api/regression/tasks/:id
- POST /api/regression/tasks/:id/cancel，body `{}`
- POST /api/regression/tasks/:id/resume，body `{}`
- GET /api/regression/tasks/:id/experiments/:experiment-id
- GET /api/regression/tasks/:id/report
- GET /api/regression/tasks/:id/bundle（停止后的可移植tar.gz，含独立复现文件与重算校验清单）

HTTP不接收任意命令、源码路径、API key或远程模型地址。没有新建多用户身份/权限；仍是受令牌保护的loopback开发服务。原有真实pytest工作区继续独立使用。

## 证据、恢复与复现

每次真实pytest实验有独立目录、HOME、临时目录、缓存，关闭自动插件加载；固定nodeid、源代码、mock组件manifest与重复序号。stages.json记录setup/call/teardown；只有完整阶段且call通过才PASS，目标断言失败才target_failure。UNKNOWN、不同错误和不稳定不合并。

执行前落盘pending；恢复时先读取原result.json，已有实验不重跑，中断缺证据实验保留并按预算追加。实验、时间和模型预算累计，不因resume清零；预算已耗尽的任务需创建新任务，不通过恢复无限追加。任务完成后不可resume，需新任务。服务退出会取消子进程；进程重启标记已失去控制器的活跃任务为interrupted，用户显式恢复。

report.json为事实源，report.md/html采用确定性模板；SHA256SUMS覆盖报告和实验文件。reproduce.py与environment.json直接重放合成失败，无需模型；工具replay创建新的replays目录，不覆盖原证据，并核对源码/环境哈希。缓存与制品不包含在git，分享重放时需要显式打包这些文件。

## 尚未接通

- 真实SDK inventory/update/prepare适配、任意登记case、真实wheel安装回退。
- LLVM/cmodel原生闭包、实际so加载与设备lease/健康恢复。
- 真实模型端点、token usage及live评测；当前仅mock决策并计调用预算。
- 网站问答、用户归属及跨任务硬件资源调度。

这些接口不能以mock结果替代真实证明。详细后续契约见REGRESSION_V1.md与REGRESSION_AGENT.md。

控制器Python缺少pytest时返回PYTEST_UNAVAILABLE，不执行实验、不归为baseline_invalid；安装测试依赖后可创建新任务或恢复原任务。

网页未连接时支持浏览器预设流程回放，默认显示完成样例，播放按钮按阶段展示；无需令牌且不请求回归任务API。该模式不执行pytest、不更新SDK、不调用模型，日志/报告为示意，不能导出真实复现证据包或可执行重放指令。连接服务后才切换到真实CPU pytest任务。
