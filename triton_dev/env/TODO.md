# env — TODO 与进度

## 当前进度

部分实现，离线流程已验证。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] SDK 扫描、日期选择、元数据和哈希
- [x] 事务下载、校验、并发锁
- [x] 离线 venv 安装和 Python wheel 来源覆盖
- [x] 变量导出、真实 shell/进程隔离
- [x] 指定解释器实际创建 venv，安装前核对 Python 版本和平台；支持 PATH 名称及带空格路径

## 本轮离线增量

- [x] 命名组合 save/list/show/diff 与 --saved 恢复：冻结选择、哈希检查、禁止覆盖
- [x] 目标解释器 wheel tags / Requires-Python / 基础依赖约束预检；未知闭包明确返回 unknown

## 待办与验收条件

- [ ] 接入真实 JFrog 列表和认证，明确可信校验来源
- [ ] 确认 SDK 归档链接策略后支持安全的内部链接
- [ ] 确认原生 ComponentMap、ABI 和加载探针，再实现 sdk-view / cmodel 混用
- [ ] 支持更完整的 wheel 平台候选和原生依赖闭包验证
- [ ] 在 Linux 多 Python 版本上验证跨版本创建；本地包装解释器测试不等于 cp310 SDK 验证
- [x] Python wheel 来源 mix 与命名组合 save/恢复
- [ ] 搜索式候选、活动环境的清理策略；原生混用仍未支持

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
