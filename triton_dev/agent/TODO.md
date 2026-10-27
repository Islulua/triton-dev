# agent — TODO 与进度

## 当前进度

离线协议原型已实现，无实时 AI。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] ScriptedModel 和严格消息校验
- [x] 只读真实 CLI Bridge、预算和重复查询停止
- [x] 伪造证据、自由 shell 和无依据 finish 被拒绝

## 本轮离线增量

- [x] 登记 recipe 的真实子进程实验、轮数/执行次数/耗时预算、累计 checkpoint
- [x] 崩溃 pending 不自动重放、证据约束 finish、ask_user 与明确停止状态

## 待办与验收条件

- [ ] 按授权机制接入模型 provider
- [x] 离线 agent 通过登记 recipe 调用公共真实运行服务
- [ ] 自动准备与多组件自适应实验规划
- [x] 离线实验状态机和 FailurePredicate 校验
- [ ] 真实 provider 驱动的自适应 regression 流程
- [x] 恢复状态、累计预算与证据引用
- [ ] 更丰富的候选问答和日志检索
- [ ] 真实 AI 的受限任务集评测，不能代替离线 tests

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。

## SDK 回归 Agent 设计（2026-10-26）

方案见 [docs/REGRESSION_AGENT.md](../../docs/REGRESSION_AGENT.md)：冻结场景、二分边界审计、双向组件替换、v2决策协议与可重放证据报告。当前仅设计，未接通live provider或原生混合环境。

2026-10-26 regression首版契约：见docs/REGRESSION_V1.md。明确baseline→update→latest顺序、earliest_verified与边界模式、合法组件闭包双向干预、配置化模型及提单重放输出；本次仅设计文档，尚未实现/调用模型。

## Regression首版实现（未提交）

已增加agent regression持久任务、真实CPU pytest实验、mock清单/update/组件/模型、二分与严格首次补扫、双向组件/组干预、预算/取消/恢复和JSON/MD/HTML/重放报告。CLI、鉴权后台HTTP和/#regression网页共用业务服务。真实SDK/任意case/模型API及原生包与板卡仍未接通。使用与边界见docs/REGRESSION_USAGE.md。

Regression验收：Python148项、前端模型14+静态4项、ruff及前端/Python构建通过；仓库外安装wheel后catalog与真实baseline/latest pytest smoke通过。网页验证单组件15日边界、非单调13日首次失败、日志/矩阵/报告，下载证据包校验及独立重放通过。当前修改未提交。

2026-10-27 多用户与数据库设计：详见docs/DATA_PLATFORM.md。姓名会话/个人workspace、个人模型profile与加密密钥、PostgreSQL事实源/证据BlobStore、统一任务/结果/daily模型、查询索引、DB租约与旧数据迁移；当前仅方案，尚未实现。
