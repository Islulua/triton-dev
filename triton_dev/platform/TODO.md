# platform — 进度与边界

- [x] PostgreSQL/SQLite repository、Alembic schema、姓名会话与 workspace 隔离
- [x] pytest/regression/profiling HTTP 适配，结果/阶段/实验/证据索引与分页
- [x] 个人 AI profile revision、加密 write-only Key、mock 协议测试
- [x] DB 队列、配额、幂等、租约、fencing、取消与保守恢复
- [x] 公共 SDK 元数据、daily 定义/幂等批次、legacy 未分配导入
- [x] 网页姓名登录、模型配置、数据中心、退出换用户清缓存
- [ ] 真实 provider 网关、usage 结算、Key 撤销/主密钥轮换
- [ ] PostgreSQL RLS、SSO、容器 Runner、设备租约与资源配额
- [ ] 制品发现、明确来源/构建选择、真实环境 Builder 与 latest 门禁
- [ ] legacy 证据全量迁移与显式管理员分配

实际使用与部署边界：docs/PLATFORM_USAGE.md。默认测试为合成 SDK 与真实 CPU 子进程；可显式启用 PostgreSQL schema 验收，不访问真实模型/板卡。
