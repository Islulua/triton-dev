# 真实环境接入清单

本机无 Triton/设备，以下不使用 mock 宣称已通过。

1. 确认 JFrog 的实际目录列表/API、认证和 digest 来源；当前仅实现并用本地 HTTP 验证 HTML 链接发现。凭据由 TRITON_DEV_TOKEN 注入，不写源码。
2. 提供真实 SDK 的归档结构，尤其软/硬链接；当前拒绝链接和特殊文件。支持链接前必须规定解析范围与测试，不能禁用路径检查。
3. 明确 wheel 依赖闭包、Python 3.10 Linux ABI、真实包 import 名称。probe 只报告模块导入路径，不等于原生功能验证。
4. 确认 cmodel、LLVM、firmware、runtime 的文件边界、加载入口、关联库和共享文件。当前 --cmodel-sdk 明确不支持，不能仅更改 LD_LIBRARY_PATH 顺序。
5. 提供实际构建配方、依赖、输出映射和版本信息。txops 不自动等于 raops，torch_txda 不自动等于 torch_raisa，暂不登记未知 cmodel 源码。
6. 固定 good/bad SDK、case、输入、参考比较和设备预算，添加 sdk_integration 门禁。不具备资源则单独报告未完成。
7. 实时 AI provider 通过 integrations/ai 接入，先使用授权的凭据机制；普通 CI 只运行离线协议。模型提案不能直接成为命令或事实。
8. Server 后续才接任务调度、取消、SSE 和身份控制；当前只读 loopback endpoint 不承诺远程服务能力。

源码目标见 build/service.py，与设计文档保持一致。SDK 根目录是否可写需管理员预先配置；工具不会自动 sudo，也不会修改权限。
