# execution — TODO 与进度

## 当前进度

子进程执行已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 真实退出码、stdout/stderr
- [x] 独立临时缓存、超时和进程组取消
- [x] Python 命令绑定明确解释器

## 本轮离线增量

- [x] runs 显式持久记录、日志上限与截断标识、原始退出码和终止状态
- [x] pytest 失败项复测、原始运行保留与阶段结果 diff

## 待办与验收条件

- [x] 大日志流式输出与大小上限
- [ ] 设备、端口和共享服务调度
- [x] pytest 阶段结果、复测和首次失败记录
- [ ] kernel 输入、编译产物和业务附件适配
- [ ] 任务恢复、终止状态和可选持久化

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
