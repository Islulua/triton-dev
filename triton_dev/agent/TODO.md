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
