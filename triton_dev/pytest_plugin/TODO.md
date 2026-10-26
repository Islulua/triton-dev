# pytest_plugin — TODO 与进度

## 当前进度

显式 collection 插件已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 参数化/markers 采集
- [x] collect-only 不执行测试体

## 本轮离线增量

- [x] setup/call/teardown 与 session 事件、worker 分文件聚合
- [x] collection 增加 fixture、行号、显式逻辑 case_id

## 待办与验收条件

- [ ] setup/call/teardown、业务 context 和失败附件
- [ ] 并行 worker 事件去重和附件隔离
- [ ] 被杀进程的未完成状态由 execution 补充

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。

## pytest 服务增量

- [x] 登记项目真实收集与参数实例选择、逐 case / session 进程运行
- [x] 冻结源码与目录/缓存隔离，解释器版本漂移检查
- [x] 真实阶段、context、显式附件、失败/全部复测与 lineage
- [ ] 设备租约、不可变环境/原生哈希验证、参数覆盖与分页存储

详细边界及验证入口：docs/PYTEST_SERVER.md、serve/tests/test_pytest_jobs.py。

## 参数配置与 xdist 增量（未提交）

- 已实现：逻辑用例分组与参数实例单选/多选；单次运行 xdist workers、每 worker 日志/进度/PID/独立缓存；失败复测保留 workers 与扩展选项。
- 扩展接口：服务登记 schema/default/version/固定编译函数，项目 allowlist；内置失败阈值、慢阶段统计和输出捕获。HTTP 不接受自由命令。
- xdist 同次运行共享源码工作目录，设备尚无租约；默认逐 case 模式保留。远程多用户身份及任意 fixture 参数覆盖仍待实现。
- 验证：Python 105 passed、ruff通过；前端模型5项和静态打包4项通过。详细使用及边界见 docs/PYTEST_SERVER.md。

## 批次统计增量

- [x] 运行总览、结果/算子/失败阶段图、最慢Top10、复测变化与图表筛选
- [x] 配置去重、未完成/跳过分母、父运行未覆盖范围和缺失耗时保护
- [x] operator显式标注收集、CPU七算子样例和JSON统计导出
- [ ] 参数热力图、Worker负载、趋势和跨任意批次对比

详见docs/RUN_STATISTICS.md；当前未提交。

2026-10-26 交付整理：本轮Profiling demo、时间线导航、运行统计、逐配置报告及紧凑布局纳入本次提交；上文“未提交”为各增量开发时记录。板卡测量仍为mock，回归agent新增内容为设计文档。
