# 迁移到本地开发

后续应用、后台任务和模型调用在本机运行。云端演示进程已停止；不需要端口转发。当前聊天无法直接控制本机，需在本地 Codex/IDE 打开项目后继续开发。

## 获取当前分支

开发分支为 `triton-dev-harness`，包含 Harness 集成、统一导航和本地化脚本。目标目录尚不存在时：

```bash
git clone --branch triton-dev-harness https://github.com/Islulua/triton-dev.git ~/workspace/triton-dev
cd ~/workspace/triton-dev
```

如果本地已有该仓库，先检查并保留未提交修改，再 fetch 并切换到该分支；不要覆盖现有目录。无需再导入先前提供的 bundle 或额外应用本地化 patch。

Git 仓库不包含云端 venv、node_modules、数据库、浏览器登录态、日志或凭据。需要保留演示数据时，应另行明确选择要迁移的数据，不能把云端数据库和密钥目录整体混入代码包。

## macOS 前置工具

已安装符合版本的 Node/Python/Git 时直接使用即可。使用 Homebrew 时：

```bash
brew install node@24 python@3.12 git
export PATH="$(brew --prefix node@24)/bin:$PATH"
export TRITON_PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
```

这些 export 仅作用于当前终端；本说明不会修改 shell 配置文件。macOS 已自带 zsh。模型凭据在本机配置，不在迁移包中。

## 本地准备

支持 macOS、Linux、Windows 的 WSL2。原生 Windows 暂不支持当前 POSIX venv/shell 脚本。需要 Git、Node.js >=24.9、Python >=3.10 和 bash；完整 shell 测试还需要 zsh。

在本机项目根目录：

```bash
bash harness/scripts/setup.sh
cd harness
npm start
```

安装脚本默认使用 `python3`，可设置 `TRITON_PYTHON=/absolute/path/to/python3`。启动后打开本机浏览器；默认页面端口 3080，后端端口 8766。使用 Harness 输出的认证入口完成首次访问。Ctrl+C 停止本次启动的两个服务。

模型 endpoint 与凭据在本机 Harness 设置中配置；不从云端复制登录态或密钥。无需真实板卡即可使用现有离线演示；真实板卡、编译器与 Profiling 的边界沿用架构文档。

## 路径与覆盖

- 项目路径从脚本位置解析，支持 checkout 路径包含空格。
- 数据与运行时默认 `~/.local/share/triton-dev-harness`；设置 `XDG_DATA_HOME` 时使用其下的 `triton-dev-harness`。
- `TRITON_HARNESS_ROOT` 可以覆盖整个本地数据根目录，setup/start 必须使用相同配置。
- `DSH_HOME` 可覆盖 Harness profile 目录，同样应在安装和启动时保持一致。
- `TRITON_BACKEND_PORT`、`TRITON_HARNESS_PORT` 可修改端口；`TRITON_NO_OPEN=1` 禁止自动打开浏览器。
- SDK、cache、demo registry、SQLite 数据库在本机重新生成；不依赖云端 `/workspace`。

## 本地验收

安装后，在项目根目录执行：

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
npm test --prefix frontend
npm run test:sites --prefix frontend
npm test --prefix harness
# 后端运行时，另开终端执行真实 CPU + mock Profiling 工具链验收
node harness/scripts/smoke.mjs
```

本次准备遵循“停止云端运行”的要求，没有在云端再次安装、启动应用或执行测试套件；本机安装与运行尚需在目标电脑上验收。
