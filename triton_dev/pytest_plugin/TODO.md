# pytest_plugin — TODO 与进度

## 当前进度

显式 collection 插件已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 参数化/markers 采集
- [x] collect-only 不执行测试体

## 待办与验收条件

- [ ] setup/call/teardown、业务 context 和失败附件
- [ ] 并行 worker 事件去重和附件隔离
- [ ] 被杀进程的未完成状态由 execution 补充

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
