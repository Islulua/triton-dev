# 多用户数据平台：首版使用说明

2026-10-27。实现位于 `triton_dev/platform/`；原 loopback/Bearer 服务保持兼容，使用 `serve --multi-user` 开启新模式。网页自动识别模式，展示姓名登录、个人模型配置、数据中心与账号空间。

## 已实现

- 姓名 NFC/空白/大小写规范化，稳定 user/workspace ID；同名回到同一空间。随机 Cookie 会话、24 小时有效期、注销撤销、同源与 CSRF 检查。
- pytest、regression、profiling 的列表、明细、日志、报告、附件、取消和复测检查空间归属；跨空间对象返回 404。名字 admin/root 没有特权。
- PostgreSQL + SQLAlchemy + Alembic 自动迁移。任务、阶段与最终配置结果、回归实验、顺序事件、模型配置、密钥版本、SDK 元数据、daily 批次和审计入库。SQLite 仅用于单进程开发。
- 文件保存大段证据，数据库保存所有权、相对位置和 SHA256；下载校验归属与内容。最终配置统计不混入 setup/call/teardown 阶段条目。
- 持久数据库队列；事务认领、generation fencing、心跳、取消、过期租约转 interrupted。旧进程可能仍在运行时拒绝直接恢复。pytest 通过复测创建新任务；regression 可明确恢复 checkpoint。
- 每空间最多 20 个排队/执行任务，服务最多 200 个；幂等重试不重复占用配额。当前每个服务进程一个执行 worker，与单次 pytest 的 xdist workers 是不同概念。
- 个人模型配置保存不可变 revision，任务锁定所选 revision；API Key 使用 Fernet 认证加密，只写入、不读回、不进入 Runner 环境。默认/启用状态按空间管理。
- 数据中心：我的任务按类型/状态分页查询，配置结果按 nodeid/结果查询，公共 SDK 元数据与 daily 批次只读查看。任务分页使用 keyset cursor。
- 管理 CLI 导入旧任务到 `legacy` 未分配空间，不自动归给首位用户；导入不会启动历史任务。管理命令不启动 worker。

## 运行

安装可选服务依赖：

```bash
python -m pip install -e '.[server]'
export TRITON_DEV_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/triton_dev'
triton-dev platform manage migrate --cache-root /srv/triton-dev
triton-dev serve --multi-user --cache-root /srv/triton-dev \
  --jobs /etc/triton-dev/jobs.json --ui frontend/dist/client --port 8765
```

URL 从环境变量读取，不应写入代码、截图或工单。数据库和 `/srv/triton-dev/platform` 需属于专用服务账号。预览默认监听 loopback；共享访问通过受管反向代理，配置 `--allowed-host HOST`，HTTPS 使用 `--secure-cookies`。不建议以 root 运行 API 和测试子进程。部署启动器应保证同一实例配置一致。

本地开发可以设置 `TRITON_DEV_DATABASE_URL=sqlite:////absolute/path/platform.sqlite`；共享部署使用 PostgreSQL。启动和迁移均通过 Alembic 到当前 schema `0002_stage_results`。

`credentials/master.key` 首次创建为 0600，父目录 0700。数据库备份和该密钥应分开保管、一起演练恢复；丢失密钥无法解密旧配置。当前没有主密钥在线轮换功能。用户更新 API Key 会新增加密版本，保留旧任务锁定的旧 revision；撤销旧 Key 的网关策略尚待实现。

## 个人操作

1. 在姓名登录框输入可区分的登录名，进入个人空间。
2. 左侧 Agent → 模型配置保存本地 mock 配置，可设默认；回归新建表单可选个人配置。
3. 在用例与运行执行已登记项目；回归定位继续使用真实 CPU pytest + mock SDK/模型适配器；Profiling 仍为模拟板卡。
4. 在数据中心查询自己的任务与结果。退出并输入另一名字切换空间，界面清理旧用户缓存和轮询；再次输入原名恢复历史。

**姓名登录不验证身份**，知道同名即可进入该空间。当前按可信内网协作管理归属，涉及真实付费密钥/外部访问时，应接入 SSO 等身份验证。

远程 `openai_compatible` 配置仅可保存管理员 `--model-endpoint URL` 登记的端点；本版没有任何外部模型请求。测试远程配置/以远程配置发起回归明确返回 `UNSUPPORTED`，不会偷偷使用其他用户配置。mock 测试标注未调用网络、不产生真实 token/费用，未记录费用显示 unknown。

## daily 与 SDK 元数据

管理命令：

```bash
triton-dev platform manage import-legacy --input /old/cache/tasks --cache-root /srv/triton-dev
triton-dev platform manage import-build --input build.json --cache-root /srv/triton-dev
triton-dev platform manage daily-plan --input daily.json --jobs jobs.json --cache-root /srv/triton-dev
triton-dev platform manage daily-tick --jobs jobs.json --cache-root /srv/triton-dev
```

`build.json` 必须恰含 source/channel/platform/build_id/build_date/components/source_kind 字段，例如：

```json
{"source":"demo-sdk","channel":"daily","platform":"cpu-demo","build_id":"20261027.1","build_date":"2026-10-27","components":{"llvm":{"version":"mock-v1","sha256":"declared-demo-hash"}},"source_kind":"mock"}
```

这是声明的元数据，状态始终 `candidate`，没有下载或验证哈希。相同内容重复导入返回同一 ID，相同版本不同内容产生新记录。

`daily.json` 示例 `{"name":"CPU daily","job_id":"registered-job","hour":8,"minute":0}`。服务每 30 秒按上海业务日期检查计划，CLI 可手动触发。批次按 definition/date/build 幂等，归系统空间；用户只通过公共批次入口查看指定系统任务。

**当前 daily 执行已登记 job 的环境，并未安装对应 SDK**，报告显式记录 `sdk_installed:false`。不能将它当作 SDK 兼容性验证或 latest 门禁；尚无真实制品发现/Builder/latest 原子发布。多来源目录应使用独立部署或接入明确的来源选择器后调度。

## 目前边界与验收

- 应用层空间检查与组合外键已落地；PostgreSQL RLS 尚未开启。
- 独立工作目录、缓存和受控环境变量不是容器安全隔离。仍需可信登记代码；设备租约、容器 Runner、CPU/内存配额留待真实部署接入。
- 时间字段为 UTC epoch 秒，daily 业务日期是上海日期；不是设计稿中拟议的 timestamptz 类型。
- 导入旧任务只建立未分配记录和原证据目录引用，不自动迁移全部旧附件；旧目录必须保留。
- 默认测试不调用真实模型、设备或内网制品。设置 `TRITON_DEV_TEST_DATABASE_URL` 可对独立 PostgreSQL schema 运行同一组隔离/队列/迁移测试。
