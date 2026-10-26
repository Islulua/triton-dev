# 测试报告预览

独立页面为 `/#reports`，左侧“测试报告”导航进入。连接本地API后选择pytest项目与运行记录，预览该记录中所选nodeid的逐配置结果。运行详情里也增加“报告预览”tab，并提供“前往阶段明细”操作。浏览器演示同样可预览，明确标注来源，无文件/时间数据时显示未记录。

## 报告结构

文件 → 逻辑用例（保留Class路径）→ 参数配置。按收集的logical_nodeid分组，不以业务case_id或算子名称合并不同函数/类；每个参数化nodeid只计一次。文件路径显示nodeid中的项目相对路径。旧记录缺失文件路径时显示“未记录文件”，不捏造目录。

每个配置的结果单元格内有固定宽度、带大写英文的色块，兼顾文字辨识：

| 色块 | 含义 |
| --- | --- |
| PASS | pytest最终配置结果通过 |
| FAIL | 配置有明确阶段失败 |
| CRASH | 有开始事件、对应worker异常退出且配置未完成 |
| SKIP | 跳过 |
| XFAIL / XPASS | 预期失败 / 意外通过，分别保留 |
| TIMEOUT / CANCELLED | 超时/取消时有执行证据的未完成配置 |
| INCOMPLETE | 终态下未执行或缺少完整报告，无法证明崩溃 |
| PENDING / RUNNING | 活跃运行中的未开始 / 运行中 |

展示参数ID与参数值、开始时间、结束/最后阶段报告时间、累计阶段耗时、worker、失败阶段。展开详细信息可看nodeid、文件行号、逻辑case_id、算子、PID、markers、fixtures、错误说明及原始阶段/context/properties。批次头部保留项目、运行ID、状态、父运行、退出码、源码哈希、Python或具名环境、隔离方式、workers和批次起止时间。

支持文件/用例展开折叠、配置搜索、状态筛选、状态图例点击。筛选只影响显示数量与分组中的局部计数，批次总数保持原始范围。较宽表格内部横向滚动，配置名称列固定。

## 时间与状态口径

- 开始采用实际test_started事件；结束使用完整结果最后一条已记录阶段事件时间，异常退出采用worker_exit事件时间。这是观察事件时间，不宣称是板卡kernel计时。
- 时间显示毫秒与浏览器本地时区；没有实际事件时间则显示“—”，不由duration反推。配置耗时为已记录阶段工时，CRASH/中断时可能只含已完成阶段，与观察窗口不同。
- CRASH由worker_exit.error、target_worker_id与最近的test_started建立关联。若同一worker先执行过别的case，已完成teardown的case不归为崩溃；从未启动的配置也不归为崩溃。
- 取消/超时中的worker终止不当成CRASH。缺少明确归属事件的单进程异常或服务中断仍显示INCOMPLETE，不根据日志字符串猜测。
- 报告显示的CRASH/TIMEOUT/CANCELLED是带证据的呈现分类，原始outcome保持不变，批次统计API也不改写。详细信息与JSON保留二者，避免影响既有复测与统计语义。
- 正确性与原生设备验证仍以case的真实证据为准；CPU demo不验证Triton算子。

## 导出与安全

“导出完整 HTML”始终导出完整所选运行，不受页面搜索/筛选/折叠影响。HTML不含脚本、CDN或外部资源，具有文件/用例分组、结果色块、时间、worker与失败证据，可离线打开或由浏览器打印。JSON导出保留展示分类与原始阶段数据。所有动态HTML文本转义；报告可能包含原始日志和本地路径，分享前检查敏感信息，不自动上传。

## 样例

`python examples/pytest_report_demo.py --workdir /new/report-demo` 生成两个文件的普通CPU测试项目（7逻辑用例、34配置）及单独的进程异常样例job。普通job仅执行test_math.py/test_memory.py；crash job明确执行test_process_exit.py，其中os._exit(17)仅退出隔离的pytest worker，不执行设备操作。两者分别运行，避免常规报告样例意外触发进程退出。

已有采集协议与HTTP路径不变，分类和HTML在本地前端生成。当前没有PDF/JUnit/Allure服务集成或完整恶意代码沙箱。

预览默认折叠文件和用例，点击分组逐级展开；“展开全部/折叠全部”控制完整层级，切换运行重置为折叠。顶部仅展示当前非零结果计数，筛选下拉仍保留全部状态。
