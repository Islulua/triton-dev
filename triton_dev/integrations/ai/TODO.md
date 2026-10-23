# integrations/ai — TODO 与进度

## 当前进度

provider 协议已定义，离线模型已验证。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] respond(context) -> dict 接口
- [x] 不让 provider 拥有执行权限

## 本轮离线增量

- [x] ScriptedModel 支持登记实验工作流离线验证；不调用真实 provider

## 待办与验收条件

- [ ] 授权模型接入、结构化响应校验
- [ ] 超时、有限重试、成本预算和 provider 版本
- [ ] 凭据接入及单独 live_ai 评测

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
