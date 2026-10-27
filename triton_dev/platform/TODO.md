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

## Daily 完整机制设计（2026-10-27）

方案见docs/DAILY_PIPELINE_DESIGN.md：SDK发现/冻结→环境构建/探针→pytest集合→报告/日历，严格全PASS判色、独立复测、数据库日志原文与索引、API/CLI一一对应。当前仅设计，现有daily仍是元数据/登记环境模式；待按文档阶段实施与真实板卡验收。

2026-10-27 Daily首版：Mock SDK/环境流水线、真实CPU pytest/xdist与算子集合选择、个人每日计划、SQL日志正文/配置结果、严格质量日历、筛选表/日志跳转/复测/导出，以及全部公开任务API的daily CLI已实现。实际接口、统计与生产边界见docs/DAILY_USAGE.md；真实SDK/任意项目suite/板卡仍待接入。
