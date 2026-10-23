# cli — TODO 与进度

## 当前进度

统一 CLI/help/describe 已实现。这是实现/验证范围描述，不是完成百分比。

## 已完成

- [x] 同一 argparse 定义生成 help/describe/capabilities
- [x] 实际候选查询、编号交互和非交互错误
- [x] 兼容 triton-env 入口
- [x] --python 帮助明确指定解释器创建与身份校验语义

## 本轮离线增量

- [x] 新增离线命令独立 dispatch；help/describe/capabilities 同源
- [x] 解析后参数对象 input_schema 与 envelope output_schema；命令结果体仍为开放结构

- [x] serve --ui 声明静态前端入口，不隐式构建或安装前端

## 待办与验收条件

- [ ] 完整输入/输出 JSON Schema 和示例生成
- [ ] 搜索式 TUI、混合配置候选联动
- [ ] 将大型 dispatch 按命令模块拆分但保持单一定义
- [ ] 命令描述副作用/重试/错误示例进一步细化

## 测试与环境

默认 tests 使用合成 SDK、受控客户端或真实本地子进程；真实 SDK/设备/模型结果必须另行记录。修改公开接口时同步更新本文件、STATUS.md、help 与 tests。
