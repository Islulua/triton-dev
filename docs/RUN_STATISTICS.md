# 批次运行统计

“用例与运行”的pytest运行详情默认进入“运行总览”，首次运行与复测均可使用。浏览器演示记录也使用相同统计组件，始终标注browser-demo，不伪造逐配置耗时。普通命令任务没有pytest配置数据，不生成测试通过数量。

## 第一版功能

- 配置数、逻辑用例数、已标注算子数、通过/失败数、通过率、执行覆盖率和批次墙钟耗时。
- passed/failed/skipped/xfailed/xpassed/incomplete/pending/running堆叠图与可点击图例。
- 按算子结果堆叠条形图，支持失败数量/失败比例/已记录累计耗时排序；各行用共同配置数量刻度。
- setup/call/teardown失败阶段图，按配置和阶段去重。
- 最慢完整配置Top10，使用实际setup/call/teardown耗时之和；未完成及缺失耗时不进入排行。
- 复测前后表，区分新增失败、已恢复、持续失败、持续通过、未覆盖/未完成、无历史结果、其他变化；未选择的父配置保留在表中，不能跳转成本次执行结果。
- 图表可筛选到“用例与阶段”，保留明确的筛选条件、匹配数量和清除筛选操作。总览图表保持整批次口径。
- 可下载带source/run_id的统计JSON；其中原始阶段/context可能含项目敏感信息，分享前需检查。没有自动上传或根因归属判定。

## 算子标注

推荐收集时显式标注，确保setup失败或skip也能归组：

```python
import pytest

@pytest.mark.operator("matmul")
@pytest.mark.parametrize("shape", [(128,128), (512,512)])
def test_matrix(shape):
    ...
```

显式加载triton_dev.pytest_plugin后注册该marker（可用于strict-markers），collection元数据新增可选operator字段，取有效非空名称，最长128字符。原始nodeid/逻辑ID契约保持不变。

也可通过triton_dev_context.update(operator="matmul")、record_property("operator", "matmul")标注；op_name字段同样接受。收集、context、property互相冲突时列为“元数据冲突”，没有标注显示“未标注算子”，不会从文件名、case_id或异常堆栈猜算子名称。逻辑用例数量按collection.logical_nodeid统计；旧记录缺失时按去参数的nodeid回退，不能把它等同算子数量。

## 统计口径

- 按request.nodeids去重限定统计范围，配置最终状态来自test_results；不信任独立summary的缓存计数，也不按阶段条数计算测试数量。
- passed/(passed+failed)为通过率；分母0显示“—”。skip/xfail/xpass单列，不自动当通过；xpass是否使进程非零仍以项目pytest策略为准。
- 执行覆盖率=有完整结果的配置数/所选配置数，完整结果包含passed/failed/skipped/xfailed/xpassed。此处是结果覆盖，**不是代码覆盖率，也不是实际设备执行比例**。
- 取消/超时/缺少报告的终态配置归incomplete；活跃运行中缺少报告为pending。没有报告不等于通过。
- 一个配置若多个阶段失败，会贡献到多个失败阶段柱，因此柱数量之和可能大于失败配置总数。最终结果仍仅计一个失败配置。
- 批次耗时=finished_at−started_at；累计配置工时按已测量完整配置计算，两者在xdist下不同。没有时间戳或逐配置时长时留空，不用平均值或演示elapsed估算。
- 复测只有明确passed→failed才叫新增失败，failed→passed才叫恢复；新加入且没有历史结果的配置单列。当前未选择或未完成不算恢复。
- 如果父运行记录可读取，将父子选择取并集以显示遗漏范围；否则只比较后端返回的已选择条目，明确标注范围不足。
- 表中源码与环境一致性来自已记录SHA256/runtime指纹，缺失即标“未记录”，不是完整原生ABI/硬件一致性证明。

## 可复现CPU样例

`python examples/pytest_statistics_demo.py --workdir /new/statistics-demo`生成7算子/34配置的真实pytest项目与jobs.json，涵盖setup/call/teardown失败、skip、xfail、xpass。测试只sleep和执行人为断言，不运行Triton kernel。登记生成的job后，收集并运行即可查看统计。

## 验证与边界

模型测试覆盖32配置去重、状态分母、未完成、缺失计时、多阶段失败、未知算子、元数据冲突和父子遗漏对照；插件测试通过真实pytest子进程验证标注收集。

图表为本地React/CSS，当前最多500选中配置，复用现有API记录刷新。此版没有新增Worker负载图、参数热力图、跨任意两批次对比、历史趋势或错误签名聚类；这些可在后续以明确元数据和可比实验范围增加。
