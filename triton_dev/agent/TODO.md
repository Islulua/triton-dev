# agent — TODO 与进度

## 当前进度

离线协议原型已实现，无实时 AI。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] ScriptedModel 和严格消息校验
- [x] 只读真实 CLI Bridge、预算和重复查询停止
- [x] 伪造证据、自由 shell 和无依据 finish 被拒绝

## 待办与验收条件

- [ ] 按授权机制接入模型 provider
- [ ] 扩展实验动作，使用准备/运行/对照的真实 CLI 契约
- [ ] 实现完整 regression 状态机和 FailurePredicate 校验
- [ ] 问答候选、恢复状态、预算和日志检索
- [ ] 真实 AI 的受限任务集评测，不能代替离线 tests

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
