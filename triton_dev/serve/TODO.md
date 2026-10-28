# serve — TODO 与进度

- [x] Bearer 模式 IR 位置解析导入与能力查询；实际编译由 multi-user SQL 服务处理。Monaco 脚本与 worker 保持同源，本地 style 动态渲染所需 CSP 已配置。

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

## pytest 服务增量

- [x] 登记项目真实收集与参数实例选择、逐 case / session 进程运行
- [x] 冻结源码与目录/缓存隔离，解释器版本漂移检查
- [x] 真实阶段、context、显式附件、失败/全部复测与 lineage
- [ ] 设备租约、不可变环境/原生哈希验证、参数覆盖与分页存储

详细边界及验证入口：docs/PYTEST_SERVER.md、serve/tests/test_pytest_jobs.py。

## 单服务器多人部署设计

目标与接口见 docs/MULTI_USER_SERVER.md（设计，尚未实现）。

- [ ] 姓名会话与任务归属，不从姓名授予管理权限
- [ ] ASGI入口、持久数据库、分页与增量事件
- [ ] 不可变环境revision、构建去重与latest发布
- [ ] 非root runner、资源预算、设备lease与恢复
- [ ] 我的环境/运行、团队报告与部署验收

## 参数配置与 xdist 增量（未提交）

- 已实现：逻辑用例分组与参数实例单选/多选；单次运行 xdist workers、每 worker 日志/进度/PID/独立缓存；失败复测保留 workers 与扩展选项。
- 扩展接口：服务登记 schema/default/version/固定编译函数，项目 allowlist；内置失败阈值、慢阶段统计和输出捕获。HTTP 不接受自由命令。
- xdist 同次运行共享源码工作目录，设备尚无租约；默认逐 case 模式保留。远程多用户身份及任意 fixture 参数覆盖仍待实现。
- 验证：Python 105 passed、ruff通过；前端模型5项和静态打包4项通过。详细使用及边界见 docs/PYTEST_SERVER.md。

## Profiling demo（2026-10-26）

- [x] 单case/模拟环境选择、预热/采样/seed、持久报告和幂等HTTP接口
- [x] 指标、采样曲线、Roofline假设模型、kernel排行、轨道时间线/缩放/事件详情、HTML/JSON/Chrome Trace导出
- [x] mock来源显式标记与适配器边界；17项新测试含真实HTTP鉴权、指标/trace一致性和非法输入
- [ ] 真实板卡工具、pytest绑定、环境revision验证、设备lease、异步取消与时钟校准

详见docs/PROFILING.md。

多引擎流水线增量：8 tiles、双缓冲、11条Matmul轨道，Tile/Buffer/依赖链、跨引擎重叠和事件筛选；Trace保留flow，HTML同步分轨。新测试验证依赖完成、同引擎无重叠、缓冲复用与时间口径；仍为mock，未提交。

2026-10-26 交付整理：本轮Profiling demo、时间线导航、运行统计、逐配置报告及紧凑布局纳入本次提交；上文“未提交”为各增量开发时记录。板卡测量仍为mock，回归agent新增内容为设计文档。

## Regression首版实现（未提交）

已增加agent regression持久任务、真实CPU pytest实验、mock清单/update/组件/模型、二分与严格首次补扫、双向组件/组干预、预算/取消/恢复和JSON/MD/HTML/重放报告。CLI、鉴权后台HTTP和/#regression网页共用业务服务。真实SDK/任意case/模型API及原生包与板卡仍未接通。使用与边界见docs/REGRESSION_USAGE.md。

2026-10-27 多用户与数据库设计：详见docs/DATA_PLATFORM.md。姓名会话/个人workspace、个人模型profile与加密密钥、PostgreSQL事实源/证据BlobStore、统一任务/结果/daily模型、查询索引、DB租约与旧数据迁移；当前仅方案，尚未实现。

2026-10-27：`serve --multi-user` 已增加ASGI姓名会话/个人workspace、统一数据库/持久队列/结果查询与个人AI配置。完整目标中RLS、SSO、非root容器Runner、真实环境Builder和设备租约仍待接入；见docs/PLATFORM_USAGE.md。
