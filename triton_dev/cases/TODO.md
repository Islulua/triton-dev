# cases — TODO 与进度

## 当前进度

真实 collection 已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 独立 pytest 进程、参数化 nodeid、markers
- [x] 收集失败不返回正常空列表

## 待办与验收条件

- [ ] 增加 show、fixture 详情和项目规范 lint
- [ ] 固定逻辑 case ID 策略和复杂筛选
- [ ] 默认禁止 collector 的外部副作用无法保证，需项目规范配合

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
