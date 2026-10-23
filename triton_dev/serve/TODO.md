# serve — TODO 与进度

## 当前进度

loopback 任务服务及可选同源静态前端；真实环境页面待接入。

## 已完成

- [x] GET /api/capabilities
- [x] 404 其他路径、无任意文件/命令入口

## 本轮离线增量

- [x] 登记任务白名单、Bearer/Host/Origin 检查、单 worker 队列、幂等与取消
- [x] 单服务目录锁、重启 interrupted、正常关闭取消、SSE 状态事件游标续读

## 待办与验收条件

- [x] 登记任务队列、进程/缓存隔离和单 worker 调度
- [ ] 真实设备健康、共享设备/端口资源管理
- [x] 持久任务状态、取消和重启 interrupted
- [x] SSE 游标续读与请求幂等去重
- [ ] Server 中的 agent 交互问答
- [x] 同源前端静态入口、Host/Origin/令牌校验与静态文件路径限制
- [ ] 远程共享部署与多用户身份策略

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
