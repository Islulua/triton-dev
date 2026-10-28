# cli — TODO 与进度

## 当前进度

统一 CLI/help/describe 已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 同一 argparse 定义生成 help/describe/capabilities
- [x] 实际候选查询、编号交互和非交互错误
- [x] 兼容 triton-env 入口
- [x] --python 帮助明确指定解释器创建与身份校验语义

## 本轮离线增量

- [x] 新增离线命令独立 dispatch；help/describe/capabilities 同源
- [x] 解析后参数对象 input_schema 与 envelope output_schema；命令结果体仍为开放结构

- [x] serve --ui 声明静态前端入口，不隐式构建或安装前端

## 待办与验收条件

- [ ] 完整输入/输出 JSON Schema 和示例生成
- [ ] 搜索式 TUI、混合配置候选联动
- [ ] 将大型 dispatch 按命令模块拆分但保持单一定义
- [ ] 命令描述副作用/重试/错误示例进一步细化

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。

## Regression首版实现（未提交）

已增加agent regression持久任务、真实CPU pytest实验、mock清单/update/组件/模型、二分与严格首次补扫、双向组件/组干预、预算/取消/恢复和JSON/MD/HTML/重放报告。CLI、鉴权后台HTTP和/#regression网页共用业务服务。真实SDK/任意case/模型API及原生包与板卡仍未接通。使用与边界见docs/REGRESSION_USAGE.md。

2026-10-27：新增serve --multi-user/database-url-env/allowed-host/model-endpoint/secure-cookies；platform manage提供migrate/import-legacy/import-build/daily-plan/daily-tick。管理命令不启动执行worker，数据库URL只从环境读取。接口与示例见docs/PLATFORM_USAGE.md。

2026-10-27 Daily首版：Mock SDK/环境流水线、真实CPU pytest/xdist与算子集合选择、个人每日计划、SQL日志正文/配置结果、严格质量日历、筛选表/日志跳转/复测/导出，以及全部公开任务API的daily CLI已实现。实际接口、统计与生产边界见docs/DAILY_USAGE.md；真实SDK/任意项目suite/板卡仍待接入。

## Kernel / IR 增量

- [x] ir import/compilers/list/compile/status/cancel 与统一 help/describe/schema；复用同源个人会话。
