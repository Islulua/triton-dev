# doctor — TODO 与进度

## 当前进度

基础只读预检已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] Python、平台、SDK、缓存权限和 shell 检查

## 待办与验收条件

- [ ] 按 prepare/build/execute 能力预检
- [ ] 真实 native runtime、设备和 ABI 条件
- [ ] 显式启用的网络/模型检查

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
