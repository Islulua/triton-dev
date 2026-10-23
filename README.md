# triton-dev

一个模块化的 SDK 环境、测试执行与证据驱动回归工具集。**v0.1 原型，无需真实 Triton 即可运行离线测试。** 所有尚未接入真实环境的能力都会标记 `not_checked` 或返回 `UNSUPPORTED`，不会伪造成功。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
source .venv/bin/activate
triton-dev --help
triton-dev capabilities --json
triton-dev describe env.prepare --json
```

工具自身安装在独立 venv，避免被 SDK wheel 切换覆盖。运行时仅依赖 Python 标准库，支持 Python 3.10+、POSIX。SDK 的 cp310/Linux x86_64 wheel 仍要求相匹配的解释器和平台；本机 macOS 测试仅证明受控逻辑。

## 已实现的最小闭环

| 模块 | v0.1 能力 |
| --- | --- |
| env | 按名称扫描 SDK、日期选择、wheel 元数据/哈希、HTTP daily 下载、校验与安全解压、离线 venv 安装、Python 包覆盖、变量导出、子进程和终端使用 |
| build | 六个源码目标的发现与 plan；实际编译明确不支持 |
| cases / pytest_plugin | 独立进程中的真实 pytest collection，包含参数化 nodeid 和 markers |
| run / execution | 测试或任意命令执行、独立临时缓存、超时和进程组取消 |
| diagnose | good/bad 重复执行、文本故障判据、基线失效判断、SDK 范围证据 |
| agent | 离线 ScriptedModel、严格问答校验、真实只读 CLI Bridge、预算、证据校验与停止；无实时模型调用 |
| report / doctor | 已有证据摘要、只读平台与目录检查 |
| serve | 只监听 loopback 的只读 `/api/capabilities`，无任务执行或前端 |

状态总览见 [STATUS.md](STATUS.md)，每个模块维护自己的 `TODO.md`，明确已完成、待办和验收条件。

## 使用

默认 SDK 根目录 `/login_home`、下载 URL 和命名规则集中在 `triton_dev/env/settings.py`。无需管理用户 YAML。`--sdk-root`、`--cache-root` 是测试/高级覆盖参数，不会修改默认配置。

```bash
triton-dev env sdk list
triton-dev env sdk inspect --sdk TX82_SDK_Daily_2026-10-22-02-52
triton-dev env download
triton-dev env download 20261022

# 显式选择解释器，预览后离线安装完整依赖组合
triton-dev env plan --sdk latest
triton-dev env prepare --sdk latest --python /path/to/python3.10
triton-dev env verify --sdk latest --python /path/to/python3.10
triton-dev env exec --sdk latest --python /path/to/python3.10 -- python -m pytest tests/smoke

# 不改变当前终端，导出相关变量（指定 SDK 必须已 prepare）
triton-dev env export --current --format sh
triton-dev env export --sdk latest --format sh
triton-dev env export --current --format json --output environment.json
```

指定 SDK 导出不会默认安装，只有显式 `--prepare` 才准备。`--current` 只读当前进程继承的 export 变量，不读取父 shell 局部变量/函数。输出含 `variables` 和 `unset`；显式文件权限设为 0600。JSON 模式输出版本化 envelope，进度和菜单不混入 stdout。

终端集成（bash/zsh）：

```bash
eval "$(triton-dev shell-init bash)"
triton-dev env use --sdk latest
triton-dev env update
triton-dev env deactivate
```

每个终端独立绑定环境；切换不会修改其他终端或已经运行的进程。`update` 获取远端最新整套 SDK，失败不应用变量；不会覆盖活动 venv。未集成时使用 `env shell` 子终端，直接 `env use` 会提示需要集成。

人工候选选择示例：`triton-dev env plan -i`；自动化使用完整参数和 `--non-interactive`。目前交互为实际候选的编号选择，搜索式 TUI、`mix/save` 是 TODO。显式的 `--cmodel-sdk` 当前返回 `UNSUPPORTED`，因为共享 lib 的组件归属未确认。

## 无 Triton 环境的演示与测试

```bash
python -m pytest -q
ruff check .
python -m build
```

测试在临时目录生成明确标记的合成 wheel/SDK，通过本地 HTTP 下载、真实 venv/pip、真实 pytest collection、bash/zsh 和并行子进程验证。不是在测试真实 Triton 或 cmodel。

`--native-only` 显式只设置原生路径，不安装/验证 SDK Python 包或实际原生库，适合受控脚本及测试适配，不可将其结果报告为完整环境验证。

```bash
triton-dev diagnose compare --good <SDK-A> --bad <SDK-B> \
  --native-only --match TARGET_FAILURE --repeat 3 -- python ./reproduce.py

triton-dev cases list ./tests --json
triton-dev build list --workspace /path/to/source-workspace
triton-dev build triton --workspace /path/to/source-workspace --plan
triton-dev doctor --json
```

`diagnose compare` 只定位 SDK 更新关联，不自动断言组件/仓库/commit 根因。错误签名不一致、基线失败、未稳定复现分别报告。

## 下载限制与真实接入

下载器实现标准 HTML 目录列表适配器，可用本地 HTTP 测试。内部 JFrog 列表 API/认证尚未在真实服务验证。可设置 `TRITON_DEV_TOKEN` 传递 bearer token；工具不打印它。真实 SDK 若包含软/硬链接，当前安全策略拒绝解压，须确认链接规则后接入，不能关掉校验绕过。

原生加载、ABI、组件混用、真实源码构建和模型 provider 均有明确 TODO。详情见 [真实环境接入](docs/INTEGRATION.md)。

## 文档

- [设计与模块契约](docs/DESIGN.md)
- [CLI 与 AI 接口](docs/INTERFACES.md)
- [开发与 CI 规则](CONTRIBUTING.md)
- [AI/代码协作规则](AGENTS.md)
- [当前进度](STATUS.md)

默认没有为每次运行生成报告文件；用户显式重定向或 `--output` 时才导出，准备状态与锁集中在工具缓存。没有第三方运行时服务或数据库。
