# 实现进度

v0.1：功能原型。未接入真实 Triton、cmodel、设备、内部 JFrog 或 live AI。默认离线测试通过不代表真实环境通过。

| 模块 | 当前进度 |
| --- | --- |
| [env](triton_dev/env/TODO.md) | 部分实现，离线流程已验证 |
| [build](triton_dev/build/TODO.md) | 接口与目标发现已实现，真实编译未实现 |
| [cases](triton_dev/cases/TODO.md) | 真实 collection 已实现 |
| [execution](triton_dev/execution/TODO.md) | 子进程执行已实现 |
| [diagnosis](triton_dev/diagnosis/TODO.md) | SDK 范围确定性对照已实现 |
| [agent](triton_dev/agent/TODO.md) | 离线协议原型已实现，无实时 AI |
| [reporting](triton_dev/reporting/TODO.md) | 已有对照摘要已实现 |
| [doctor](triton_dev/doctor/TODO.md) | 基础只读预检已实现 |
| [pytest_plugin](triton_dev/pytest_plugin/TODO.md) | 显式 collection 插件已实现 |
| [serve](triton_dev/serve/TODO.md) | 只读 loopback HTTP 原型 |
| [common](triton_dev/common/TODO.md) | 公共文件与进程能力已实现 |
| [cli](triton_dev/cli/TODO.md) | 统一 CLI/help/describe 已实现 |
| [integrations](triton_dev/integrations/TODO.md) | 适配边界已建立 |
| [integrations/shell](triton_dev/integrations/shell/TODO.md) | bash/zsh 核心流程已验证 |
| [integrations/ai](triton_dev/integrations/ai/TODO.md) | provider 协议已定义，离线模型已验证 |

## 验证记录

- 本地：Python 3.14 / macOS，合成 SDK、真实本地 HTTP、pip/venv、bash/zsh、pytest collection 和并发子进程。
- Linux/Python 3.10、3.12、3.14：由 GitHub Actions 的 offline-ci 持续看护；最终结果以 workflow 为准。
- 真实 SDK、编译、设备和 AI：TODO，接入条件见 docs/INTEGRATION.md。
