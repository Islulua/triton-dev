# integrations/shell — TODO 与进度

## 当前进度

bash/zsh 核心流程已验证。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] shell-init、当前终端 use/update/deactivate
- [x] 安全引用、恢复原变量和稳定工具入口

## 待办与验收条件

- [ ] 更完整的 shell 启动配置和嵌套原 venv 兼容测试
- [ ] 交互 TTY、持续会话缓存及失败回滚扩展

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
