# 开发与 CI

## 本地验证

```bash
python -m pip install -e '.[test]'
python -m pytest -q
ruff check .
python -m build
```

每个模块维护 tests/、TODO.md；公开接口、帮助说明、候选行为和实际执行结果一起修改。新增流程同时补跨模块测试。离线 mock 演示见 examples/offline_demo.py；安装包验证使用 examples/wheel_smoke.py，指定已安装 pytest 的 --test-python。TODO 使用具体验收条件，不用无依据的完成百分比。

## CI

GitHub Actions 在 Ubuntu 的 Python 3.10/3.12/3.14 上安装工具，执行 lint、离线模块测试、合成 wheel 真安装、shell/HTTP/CLI 流程、构建分发包和 wheel 安装入口 smoke。bash/zsh 都在目标 Linux CI 安装并执行。

离线 tests 不依赖真实 SDK、模型或设备。预留 sdk_integration/nightly/live_ai markers 不代表已有真实测试；接入后应使用独立流水线，缺少必需资源不能以 skip 冒充通过。

## 进度维护

STATUS.md 是模块索引，详细 TODO 在各模块目录。实现与真实验证分开记录：合成 SDK PASS 不等于真实 SDK PASS。新增 build 配方必须由对应项目确认，未知原生边界保持不支持。

默认不引入无关重构或通用插件平台。先完成真实需求闭环，再按证据抽公共能力。
