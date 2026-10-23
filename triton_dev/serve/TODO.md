# serve — TODO 与进度

## 当前进度

只读 loopback HTTP 原型。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] GET /api/capabilities
- [x] 404 其他路径、无任意文件/命令入口

## 待办与验收条件

- [ ] 任务队列、执行隔离与资源管理
- [ ] 持久任务状态、取消和重启 interrupted
- [ ] SSE 重连、agent 问答和去重
- [ ] 网页、身份/来源保护和共享部署策略

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
