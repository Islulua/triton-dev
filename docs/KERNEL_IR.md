# Kernel Lab 工作台

集成在现有 triton-dev 网页 `/#kernel`；没有修改 Triton、FlagTree 或真实 SDK。

## 查看与对比

- 默认 vector_add 是手写交互示意，未执行编译。源码和四个主要阶段均明确标注来源。
- 导入 TritonParse 内嵌源码/IR 的 JSON、NDJSON 或 gzip。每个 specialization 保留为独立记录。只读 `file_content`，不会访问 trace 内的磁盘路径。
- 连接服务时使用固定版本的 TritonParse 位置解析器，支持 MLIR loc、LLVM dbg、PTX/AMDGCN/SASS 和内联 callsite。CoreIR/TxIR 使用通用 MLIR 位置解析。
- 离线浏览器可以读取已经包含 `source_mappings` 的 trace 或规范化导出；原始 IR 解析需要连接服务。
- 阶段由实际文本产物决定。SO/cubin 等二进制不作为文本展示。无位置元数据明确显示“无位置映射”。
- 源码点击联动各 IR；IR 点击反向定位。映射基于同一源码快照的完整路径、起始行、内容及位置，不以文件名猜测。
- 可添加至多六个 IR 面板，选择阶段/编译记录、锁定版本、关闭联动、切换网格，或弹出独立浏览器窗口。独立窗口与原工作台通过同源随机 BroadcastChannel 联动；原工作台关闭或换用户后清除内容。
- 修改源码后立即停止旧映射。重编译期间保留原 IR，旧任务结果进入历史，不覆盖后续编辑。每面板可选其他记录的同阶段 diff。
- 导出当前完整源码/阶段/映射为 JSON。导入文件的“已编译”声明不被当作本服务验证，重新标记为导入记录。

输入上限 2 MiB、解压后 8 MiB、每次最多 50 个实例。复杂未解析位置图有额外预算，超限明确拒绝；可拆分或导入预先计算的映射。解析在线程中进行，限制并发。

## 实际编译

`serve --multi-user` 的 SQL 队列支持 `ir` 任务，复用 Cookie/CSRF、workspace 归属、幂等、租约、超时及取消。无额外数据库迁移。

管理员通过 `TRITON_DEV_IR_COMPILERS=/absolute/compilers.json` 登记隔离执行器，配置只在服务器读取，不通过 HTTP 接受可执行路径/自由 argv：

```json
{
  "tx82-sdk": {
    "label": "TX82 固定 SDK",
    "isolation": "external",
    "launcher": ["/srv/triton-dev/bin/isolated-triton-compile", "{workdir}"],
    "timeout": 60,
    "env": {}
  }
}
```

这里的 launcher 是部署方提供的实际隔离启动器，不是已打包的命令。它应将任务目录挂载为可写工作区、SDK/编译工具只读挂载，在隔离的工作目录中执行 `python worker.py`；禁止网络、服务目录和凭据访问，限制内存/CPU，并确保取消/超时清理所有子进程。登记 `isolation=external` 是管理员对该契约的显式声明，不会自动创建容器。未配置时编译不可用，不回退到 API 账号执行 Python。

任务目录输入：`kernel.py`、`spec.json`、`worker.py`。Worker 从已安装 Triton 导入 ASTSource、GPUTarget 和 compile，以显式签名/constexpr/target 编译，提取 `compiled.asm` 文本阶段，写 `artifacts.json`。支持 ASTSource 的 constexprs/constants 参数差异。服务不启动编译出的 kernel。

执行器可通过固定 `env` 指定所需工具路径；API 父进程环境不整体继承。每任务独立缓存。配置摘要冻结，排队期间登记改变会拒绝执行。编译输出作为不可信文件处理，拒绝符号链接、非普通文件、过大文件和非有限 JSON。

网页配置包括参数类型、constexpr、target、options。自动编译在源码或配置停止修改 800ms 后提交，提交新任务前取消仍在进行的旧编译。该时间为触发延迟，不承诺完成时延。编译成功仅代表编译接口成功，不证明运行正确性或板卡质量。

本机没有内网 TX82 SDK，实际 LLVM/MLIR 工具、链接器、后端目标参数和 loc 保留仍需内网验收。当前没有阶段提前停止或任意 pytest 自动捕获。

## API 与 CLI

| API | CLI |
|---|---|
| GET /api/ir/compilers | ir compilers |
| POST /api/ir/import，base64 data | ir import FILE（本地解析） |
| GET /api/ir/compilations | ir list |
| POST /api/ir/compilations，spec/idempotency_key | ir compile --file SPEC --idempotency-key KEY |
| GET /api/ir/compilations/:id | ir status ID |
| POST /api/ir/compilations/:id/cancel | ir cancel ID |

```bash
triton-dev ir import examples/ir_demo.json --json
triton-dev describe ir.compile --json
triton-dev daily login --name developer --server http://127.0.0.1:8765
triton-dev ir compilers --server http://127.0.0.1:8765
triton-dev ir compile --file compile-spec.json --idempotency-key edit-001
```

IR 客户端复用 daily login 的同源 0600 会话文件，支持 --server / --session-file。编译规格字段恰为 compiler_id/code/entry/signature/constexprs/target/options/revision。compile 退出 0 只表示成功提交；结果用 status 查询。

原 Bearer 服务提供鉴权导入及空编译能力查询；编译与持久历史需要多用户服务。

## 上游归属

TritonParse 固定提交 `a573a10384ec519dcc485a9c3c7354f35538f4e8`，位于 `triton_dev/ir/vendor/`，保留 BSD-3-Clause LICENSE。仅把日志依赖替换成标准库。前端使用本项目自己的多面板控制与规范化文档模型；编辑器、worker、字体均本地打包，不访问 CDN。
