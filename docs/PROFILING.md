# Profiling demo：单 case × 单环境

此增量是 server 的离线演示，**没有执行 pytest 或板卡测试**。网页始终标注 mock_board、假设规格、模拟计数器与正确性 not_checked。三个 case、两个环境来自专用模拟 catalog，不冒充已登记 pytest 项目或真实 SDK 环境。

## 体验

已有 `serve --jobs ... --ui frontend/dist/client` 服务增加 Profiling 导航入口。未连接时可查看内置示例；连接本地 API 后，选择 case、环境、预热/采样次数与 seed，点击“生成模拟报告”。结果持久保存在服务 tasks/profiles 下，不覆盖历史报告。相同幂等键重试返回原报告；改变参数复用键报冲突。

当前 mock catalog：Matmul fp16 1024³ / 4096³、Softmax fp32 1024×4096；环境 baseline / candidate 为假设版本快照。candidate 假设 kernel 时间乘以1.23，用于演示环境差异，不代表任何真实版本退化。

报告有平均/P50/P95设备耗时、有效算力、估算带宽、重复采样曲线、Roofline假设模型、kernel排行和事件时间构成。时间线分CPU调度、DMA拷贝和Device stream，支持采样范围、1/2/4/8倍缩放与事件详情。另可查看环境/计数器原始元数据，下载独立HTML报告、原始JSON和Chrome Trace JSON。

## 假设的板卡返回结构

`MockBoardProfiler.capture(request)` 返回独立的版本化 capture：

```json
{
  "schema_version": 1,
  "source": "mock_board",
  "case": {"id": "matmul-1024", "nodeid": "tests/test_matmul.py::test_matmul[fp16-1024]", "shape": [1024,1024,1024], "dtype": "fp16", "flops": 2147483648, "bytes": 6291456},
  "environment": {"id": "mock-baseline", "revision": "mock-sdk-20261022-r1", "packages": {"triton": "mock-3.2-baseline"}},
  "device": {"id": "mock-board-0", "name": "Mock Accelerator A1", "peak_tflops": 120, "peak_bandwidth_gbs": 900, "source": "assumed_demo_spec"},
  "samples": [{"iteration":0,"device_us":72.1,"wall_us":504.3}],
  "events": [{"id":"e0","name":"matmul_fp16_tile128","category":"kernel","track":"Device / stream 0","start_us":280,"duration_us":67.7,"iteration":0,"source":"mock_board"}],
  "counters": {"occupancy_pct":63,"memory_peak_mib":8.4,"source":"simulated_counters"},
  "warmup_excluded":3
}
```

该片段仅展示字段，不是完整可计算记录。完整样例见 frontend/src/profiling-preview.json，其内容由同一Python mock适配器生成并以测试验证一致。

## 指标口径

- 新版model_version=2的device_us是设备流水线首个输入搬运至最后Fence的窗口；kernel_work_us独立累计kernel工时。wall_us额外包含Host提交与收尾。旧报告保留kernel_sum口径，不改写历史。预热不进入samples或统计；mock只生成预热随机序列，不声称执行预热设备代码。
- P50为中位数，P95为nearest-rank；采样次数1..100，预热0..20，seed0..65535，严格整数。
- TFLOP/s = 假设FLOPs / (平均device_us × 10⁶)。GB/s = 估算字节数 / (平均device_us × 1000)。GB使用十进制。
- Roofline上界 = min(假设峰值算力, 算术强度 × 假设带宽 / 1000)；算术强度=FLOPs/估算流量。输入输出尺寸不能反映真实DRAM重复访问/缓存命中，因此不能据此确认瓶颈或根因。
- kernel占比使用所有kernel事件耗时之和作分母；时间构成使用记录事件之和，排除间隙。新版包含跨引擎重叠；事件累计时间占比不是墙钟构成。并发引擎数与重叠时间由区间扫描计算，Host wait与Fence不算活跃计算/搬运引擎。
- Occupancy、memory peak为独立假设计数器，不是根据时长推算的实际硬件计数器。

## HTTP 接口

均沿用已有loopback、Bearer、Host/Origin校验；依赖启用了登记任务的server。工具默认测试不访问板卡或私网。

| 方法 | 路径 | 内容 |
| --- | --- | --- |
| GET | /api/profiling/catalog | mock cases、环境、板卡假设及参数范围 |
| POST | /api/profiling/reports | 同步生成有界mock报告，state=generated |
| GET | /api/profiling/reports | 报告摘要列表，最新在前 |
| GET | /api/profiling/reports/:id | 完整原始报告 |
| GET | /api/profiling/reports/:id/html | envelope.data.html为无脚本、无外部资源的独立可视化HTML |
| GET | /api/profiling/reports/:id/trace | envelope.data为Chrome Trace对象 |

POST全部字段严格校验，不接受额外命令/路径/插件：

```json
{"adapter":"mock","case_id":"matmul-4096","environment_id":"mock-candidate","warmup":3,"repeats":20,"seed":42,"idempotency_key":"profile-demo-001"}
```

上限200份报告，满后明确PROFILE_LIMIT，不自动删除。读写原子化，创建与幂等检查使用进程文件锁。错误包括INVALID_PROFILE、PROFILE_NOT_FOUND、UNSUPPORTED、IDEMPOTENCY_CONFLICT。GET不会通过网络自动获取或上传trace。

## 开源参考与后续复用

- [Perfetto UI](https://perfetto.dev/docs/visualization/perfetto-ui)支持浏览器轨道时间线和legacy JSON trace，主项目[Apache-2.0许可证](https://github.com/google/perfetto/blob/main/LICENSE)。
- [PyTorch Profiler](https://docs.pytorch.org/docs/stable/profiler.html)提供kernel统计与Chrome Trace导出，适合作为真实Torch采集后端。
- 此demo自主实现轻量React报告，借鉴上述组织方式与通用trace格式，没有复制或内嵌它们的源码，也不宣称已接入完整Perfetto viewer。导出的JSON可手动在Perfetto中打开；当前未自动向外部站点传输报告。
- 后续若内嵌或自托管Perfetto，应固定版本，保留对应LICENSE/NOTICE并检查打包依赖许可证；内网部署无需依赖公网viewer。

## 真实板卡接入边界（待实现）

BoardProfiler Protocol预留capture(request)采集契约，当前只实例化MockBoardProfiler。传adapter=real/board会返回UNSUPPORTED，不会回退成“真实测试成功”。summarize目前只接受mock schema，真实适配器还需增加事件/计数器校验、时钟域校准、单位/缺失值处理。

真实流程应登记允许的case nodeid和不可变环境revision、取得设备lease、启动非root受控runner、明确预热/测量/同步窗口、回收超时进程和设备状态，再解析板卡工具输出。结果要保留工具版本、板卡标识、源码/环境哈希、原始采集文件和正确性报告引用。长时间采集必须迁入异步队列并提供取消，而非在当前同步HTTP demo中执行。独占profiling默认workers=1，不能与xdist多worker争用同一板卡；需要与设备调度一起实现。

独立HTML含指标卡、采样曲线、kernel排行、第一采样多引擎事件图和完整环境元数据，离线打开或打印即可查看；完整版时间线缩放仍在工作台内。直接入口为 /#profiling。

## 多引擎流水线增量

model_version=2：每次采样8 tiles，2个缓冲槽轮换；11条Matmul轨道（CPU提交/等待、DMA H2D/D2H、SDMA load/store、Matrix cluster0/1、Vector core0/1、Sync fence）。Softmax只使用向量计算，不伪造矩阵引擎事件。

依赖为submit→H2D→L2/SRAM load→Matrix或Vector主计算→Vector epilogue→SRAM/L2 store→D2H→Fence。Tile i重用缓冲槽前还须等待Tile i−2的Fence；引擎队列各自串行，不同引擎可以并行。默认Matmul每个采样58个事件，并非58个kernel。所有调度规则与带宽均为示例假设。

事件新增tile、buffer_slot、depends_on；Chrome Trace附带s/f依赖flow；网页点击事件显示直接父/子依赖连线，并可逐个追踪父事件、按事件类型筛选、缩放。旧报告仍按其原始轨道展示。

summary新增engines（busy_us按区间并集计算，window_pct分母为全部样本wall_us之和）、concurrency（仅kernel/transfer，重叠率分母为设备流水线窗口之和，峰值是同时活跃的引擎数）、kernel_work_mean_us和timing_basis。引擎队列串行保证一个事件对应单个活跃引擎，累计引擎时间不能直接当设备耗时。HTML输出同样使用按引擎轨道布局。

## 时间线快捷导航

鼠标悬停在时间线滚动区域，或键盘聚焦时间线/事件时：W / + / = 放大，S / - 缩小，A/D或左右方向键水平移动（Shift加速），0复位至1×和最左端，Home/End到两端。缩放支持1..32倍，和下拉框同步；连续滚轮缩放会显示当前自定义倍率。

Ctrl或⌘+滚轮以指针所指时间为中心缩放；Shift+滚轮水平移动。普通纵向滚轮保持页面滚动，触控板原生横向滚动保留。快捷键不在输入框/下拉框编辑时触发，不接管Ctrl/⌘组合键，离开时间线且焦点在外时不影响页面。离线HTML为静态报告，不提供此交互。

时间线左侧引擎名称列与ENGINE/TRACK表头固定在水平视口左侧；右侧刻度、事件和依赖线随水平平移。缩放的键盘默认锚点为名称列右侧的绘图区中心，指针位于名称列时使用绘图区左边界。
