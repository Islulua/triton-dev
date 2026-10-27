# 前端设计验收

final result: passed

## 对照依据

- 源图：`design/reference.png`，用户选择的第一种浅色 / 青绿方案。
- 构建版：`http://127.0.0.1:8765/`，Python 服务同源加载生产构建。
- 最终截图：`design/implementation-desktop-final.png`。
- 全景并排：`design/comparison-final.png`；抽屉细节并排：`design/drawer-comparison-final.png`。均实际打开检查，左为源图，右为实现。
- 相同状态：环境与制品、5 条组合、baseline 选中、创建组合抽屉打开，未连接 API。
- 最终桌面 CSS viewport 1487×1058，源图和实现均 1487×1058，devicePixelRatio=1，最终截图无需缩放。
- 前期 v2 截图来自 DPR=1.4 的浏览器合成画面，裁出 1062×756 的有效内容后缩放至 1487×1058；该归一化仅用于前期比较，最终改用 DPR=1 原始截图。

## 修复与复验历史

1. P1：搜索框吸收 flex-column 剩余高度，挤压表格。证据 `design/implementation-desktop-v1.png`；固定直属搜索框 flex-basis=43px，v2 已恢复正常表格位置。
2. P2：表格文字偏小、区域间距偏离源图。证据 `design/comparison-v2.png`；调整组合名称/状态/次要文字字号及标题、工具栏、搜索框间距。最终全景保持导航、表格和抽屉的比例与内容层级。
3. P2：390px 窄屏根页面溢出、抽屉左边界为负。证据 `design/native-mobile-drawer.png`；为表格滚动容器设定位，限制隐藏表头的定位范围，抽屉宽度改为容器百分比，并允许工具栏换行。最终根页面 scrollWidth=375≤390，抽屉 left=0。
4. P2：桌面抽屉字号偏小，原生提示被挤入滚动区。调整 input/select=16px、hint=14px、字段 gap/margin 和原生区域间距。最终细节对照中原生提示与固定底部操作均可见，字段层级接近源图。

以上 P0/P1/P2 均已修复并复验；当前无阻塞项。

## 必检视觉面

- 字体：系统字体栈 SF/PingFang/微软雅黑；标题、导航、表格和表单保持层级，英文版本串单行，长值 select 可选择查看。源图字体无法精确识别，系统字形、字重和抗锯齿有轻微差异，列为 P3。
- 间距：桌面导航 216px、顶部 60px、抽屉 436px，主区 30px 内边距；固定底部操作、表格行与横向滚动独立。1024×900 和 390×844 均无根页面横向溢出。
- 颜色：白色表面、浅灰分隔、青绿选中和主按钮；成功、失败、未验证有文字及图标，不只依赖颜色。提示文字较淡，保留了源图的次要层级；尚未进行 WCAG 自动对比度认证。
- 图片：真实源图裁切的品牌标记 `public/assets/brand-mark.png`，比例与清晰度可接受，无占位头像或 CSS 插画。标准 Tabler 图标统一线宽；未逐像素复刻生成源图中的不规则图标。
- 文案：将虚构局域网连接改为真实未连接状态；Torch 采用项目的 torch_raisa 示例名；导入通过与原生/设备未验证分开，页面始终说明演示范围。属于有意的业务修正。

## 浏览器与功能证据

- 组合重名错误、搜索空结果、组合创建/演示验证、来源比较；用例选择与参数修改；确定性失败、M=64 成功、复测新 ID、原记录保留及取消；诊断固定观察已操作验证。
- 390px：抽屉焦点循环、Escape 关闭、导航展开及进入设置；截图 `design/mobile-drawer-final.png`、`design/mobile-list-final.png`。
- 1024px：设置连接、表格内部滚动与组合抽屉；截图 `design/tablet-final.png`。
- 本地真实任务成功日志：`design/native-api-task.png`；取消终态：`design/api-cancel-final.png`，job long-demo，进程组停止，退出码 -15，事件包含 cancel_requested→cancelled。任务 ID 保留在记录中。
- 最终构建版 console warn/error 检查为空。
- 自动验证：Python 88 passed、ruff 通过；前端模型测试 4 passed，静态打包测试 4 passed；npm build、sdist/wheel 与仓库外安装 smoke 通过。

## 余留与范围

- P3：系统字体、细小图标、主按钮宽度与生成稿有轻微差异。窄屏表单内容滚动，底部操作保持可见。
- 未进行屏幕阅读器、多操作系统字体或完整 200% 缩放测试；不宣称完成无障碍认证。
- 真实环境/用例/诊断 HTTP、kernel 设备与实时 AI 待接入；通过本报告只表示当前原型的视觉及已描述交互通过，不代表真实 SDK 或数值正确性通过。

## 实施清单

- [x] 同尺寸桌面对照、抽屉细节对照
- [x] 修复搜索框、排版与窄屏溢出并重新截图
- [x] 验证真实任务成功与取消，检查控制台
- [x] 保留演示/真实任务边界
- [ ] 后续接入真实业务 API 后重做对应页面验收

## pytest 工作区增量验收

final result: passed

- 新增屏幕无对应的同内容生成稿，继承选定源图的导航、白色表面、青绿主色、表格和字体层级。`design/pytest-layout-comparison.png` 并排放入原稿与真实结果页，明确是不同业务状态，不能用于声称内容逐像素一致；`design/pytest-navigation-comparison.png` 用于检查共用导航。两张并排图已打开检查。
- 最终桌面截图 `design/pytest-result-final.png`：CSS viewport 1487×1058，DPR=1，原始内容截图1472×1047；并排画布右/下方留白对齐源图1487×1058，未拉伸内容。
- 字体/排版：参数化 nodeid、阶段、统计和日志使用不同层级；路径和堆栈可换行，日志在面板内滚动。源码页继续使用前轮风格，无新建自定义插画。
- 颜色/资产：复用品牌图片与现有浅色青绿 token，成功/失败/跳过都有文字，未伪造 SDK 或设备验证状态。图标和系统字形的细微差异沿用前轮P3。
- 内容：真实 pytest 阶段与浏览器演示明确分开；CPU工作流样例明确写明未执行 kernel，8项统计为3通过、3失败、1跳过、1预期失败。
- 实际操作：收集8个参数实例、选择全部、逐case运行、点击失败项复测生成3项子记录、查看before/after及失败阶段、下载显式附件、服务重启后读取历史。环境指纹检查曾发现元数据搜索路径重复导致误报，已按包名/版本去重，保留错误尝试并验证旧快照可继续复测。
- P2手机问题：复测说明的匿名flex文本被挤成窄列，初始证据 `design/pytest-mobile-final-native.png`；修为块级正常换行，复验图 `design/pytest-mobile-fixed.png`。最终CSS390×844、DPR=1，根scrollWidth=375，无水平溢出；说明区宽339、高88，文本可读。原始DPR1.4捕获只作历史证据，不用作最终同尺寸比较。
- 最终浏览器控制台warn/error检查为空。布局修复后无尚需处理的P0/P1/P2；小屏需滚动查看长报告，属于预期行为。
- 自动验证：完整Python97 passed、ruff通过；前端模型4项、静态打包4项通过；前端构建、sdist/wheel构建、仓库外安装的SDK/pytest阶段/证据及服务收集/运行/复测smoke通过。
- 未覆盖：实际设备/容器、多用户、大量历史分页、屏幕阅读器及全平台字体。验收不宣称真实kernel或原生ABI通过。

## 配置选择与 xdist 增量验收

final result: passed

- 用户提供旧版扁平用例表作为问题示例；新增逻辑用例分组、配置行、执行设置和 worker 日志，延续既有浅色青绿界面，不宣称与旧表逐像素相同。
- 浏览器实际验证：32配置中只选cfg-17，运行结果仅1项通过；选40配置、Workers=4，真实4个PID、39通过和1个刻意失败，每个worker有实际输出；捕获与主动进度日志分开说明。
- 配置单选证据：design/xdist-single-config-content.png。Worker证据：design/xdist-workers-final-content.png。源截图对应 -final.png；CSS viewport1487×1058、DPR1.4，原生截图1476×1051的有效内容约1062×756，裁除空白，未缩放。裁图仅用于查看功能，不作为同尺寸像素比对。均已打开检查。
- 桌面：层级、统计、实际PID卡片与日志过滤清晰，日志内部滚动；复用字体、品牌图片和颜色，未增加插画。文本、状态兼有明确标签。
- 手机：CSS390×844、根scrollWidth379，无根水平溢出；worker卡片两列，长日志内部滚动，截图design/xdist-mobile-workers.png。原生DPR截图有合成缩放与空白，不用于尺寸测量。
- 控制台warn/error为空；Python105项、前端模型5项/静态打包4项通过，ruff与构建通过。安装包另有真实xdist执行smoke。
- 无新增P0/P1/P2；保留系统字形等既有P3，屏幕阅读器、真实硬件并行和跨平台字体尚未验证。

## Profiling demo 增量验收（2026-10-26）

final result: passed

- 继承现有浅色青绿设计，新增Profiling导航与单case/环境/预热/采样表单。报告布局含元数据、4项指标、采样曲线、Roofline与kernel排行；时间线单独分tab，长时间线内部水平滚动。
- 真实浏览器操作：candidate + matmul-4096 + warmup3/repeats12/seed42，经本地API生成报告；非法repeats=0被拒绝，报告没有覆盖。时间线2×缩放、kernel详情有效。Trace下载读回为60事件/3轨道/原环境版本。
- Chrome Trace参照Perfetto兼容格式，无外部上传；独立HTML报告无脚本和外部资源，已在本地浏览器打开验证指标、曲线、事件图与原始元数据。
- CSS桌面1487×1058，手机390×844；手机根scrollWidth379无横向溢出，时间线/表格有内部滚动。
- 截图：profiling-overview-desktop-content.png、profiling-timeline-detail-content.png、profiling-mobile.png、profiling-html-native-content.png。工作台原生DPR1.4截图1476×1051有效内容约1062×756，-content仅裁空白、不缩放；独立HTML截图为1265×712，保留全部内容不裁切；fullPage截图存在右侧截断，只作历史记录，不作为最终依据。以上图已打开检查，非与旧稿同业务状态逐像素比对。
- 系统字体、白表面、teal主色和Tabler图标延续既有设计；图表为数据SVG，无新增图片资源。mock/假设/未验证在页面与导出里保留。
- 无新增P0/P1/P2。保留系统字形等既有P3；屏幕阅读器、跨系统、真实板卡与超大trace未验证。
- 验证：Python122通过（17项profiling）、ruff通过、前端5+4通过、前端和Python构建通过、sdist含fixture、仓库外安装后的capture/report/trace/HTML smoke通过。

## 多引擎流水线增量验收

- 8 tiles、双缓冲，默认Matmul 11轨道；每采样58事件，显示跨引擎重叠。按kernel筛选剩4轨道；选Tile4矩阵事件有2条直接依赖连线，详情含Tile/Buffer/上游事件。
- 桌面CSS1487×1214、390px手机根scrollWidth379；截图profiling-pipeline.png（原生DPR1.4截图裁除空白，无缩放）、profiling-pipeline-mobile.png。已检查桌面分轨布局、颜色、事件标签和依赖箭头，沿用既有字体/品牌，无新增P0/P1/P2。长时间线在内部横向滚动，11行通过页面纵向滚动查看。
- 新版HTML按引擎而非按单事件分行，Chrome Trace含s/f依赖flow。原始报告和历史口径保留，model_version=2采用pipeline span。
- 完整Python125项、ruff、前端5+4项通过。新增3项参数化测试覆盖三种case的依赖排序、同引擎互斥、双缓冲复用、流水线时间与flow一致性。设备数据均为mock。

## 时间线快捷导航验收

- 悬停/焦点范围的快捷键、指针锚定滚轮缩放和Shift滚轮横移已实现；倍率1..32与下拉框同步。默认滚轮不拦截，编辑输入框和下拉框时不接管单键导航，卸载清理全局监听。
- 实际浏览器验证W变2×、D令scrollLeft增大、0恢复1×/scrollLeft=0，输入焦点ArrowRight不改变时间线倍率；控制台warn/error为空。锚定时间计算与浏览器modifier键保留由模型测试验证。
- 提示与焦点样式截图profiling-shortcuts-final.png，原生DPR截图裁空白不缩放；没有更改原有轨道与配色，无新增P0/P1/P2。模型6项、静态打包4项及构建通过。

## 固定引擎名称列

- 使用不透明sticky标签层固定左侧名称与ENGINE/TRACK表头，依赖路径绘制在标签层下。缩放锚点限制在绘图区，默认使用绘图区中心。
- 独立浏览器页验证：水平scrollLeft从0到701、事件left从437到−264，名称列left保持247；滚动到End（963）后全部11行标签和表头仍贴齐容器左缘。截图profiling-fixed-column.png已检查。
- 前端模型6项和构建通过，差异空白检查通过，无新增P0/P1/P2；修改未提交。

## 批次统计增量验收

- 默认运行总览：配置数与逻辑用例/显式算子分别显示；状态堆叠图、算子结果条形图、失败阶段、最慢配置和复测变化，沿用浅色青绿界面。统计基于实际记录，浏览器demo单独标注，无计时处留空。
- 真实CPU pytest执行7算子34配置：26通过、5失败、1skip、1xfail、1xpass，覆盖setup/call/teardown。图表点击matmul失败和teardown失败均进入筛选详情；浏览器demo也验证单配置联动。
- 仅复测5项失败：持续失败5，父记录未覆盖29，点击未覆盖过滤显示29条“本次未执行”；统计下载读回确认未覆盖29、恢复0，不把遗漏项算恢复。控制台warn/error为空。
- 模型10项（新增4项边界统计）和静态打包4项通过，Python126项与ruff通过；前端/Python构建通过。
- 桌面CSS1487×1058，截图run-statistics-desktop-final.png；首屏run-statistics-overview.png；复测run-statistics-rerun.png。手机CSS390×844、根scrollWidth375，截图run-statistics-mobile.png；导航的过渡捕获一度遮挡，复验完成后sidebarRight=0，已覆盖过渡截图。已实际查看这些图表与手机图，无新增P0/P1/P2。系统字体等已有P3不变，不宣称无障碍认证。
- 真实板卡、热力图、Worker负载图和跨任意批次比较未包含在本轮。

## 逐配置测试报告验收（2026-10-26）

- 独立测试报告页与运行详情的“报告预览”均已通过实际浏览器操作验证；2文件、7逻辑用例、34配置按层级展开，结果单元格包含PASS/FAIL等有文字的色块。最新构建复验退出码1、父运行与真实毫秒时间。
- 实际CPU pytest样例：26 PASS、5 FAIL、1 SKIP、1 XFAIL、1 XPASS；搜索4096、结果筛选、详情展开、全展开/折叠均有效。完整HTML下载读回确认34配置、两文件及毫秒时间。
- 实际异常退出样例：仅最近已开始且尚无完整报告的配置标CRASH（1条），2 PASS和5 INCOMPLETE保持独立；未将未启动配置全部标崩溃。原始outcome不修改。
- 桌面CSS1487×1058、手机390×844；根scrollWidth分别1472/375，表格内部水平滚动。已打开检查case-report-preview-final.png与case-report-mobile.png：文件/用例层级、参数、结果色块和表格对齐清楚，手机筛选和分组正常。另存case-report-preview-top.png和case-report-crash.png。控制台warn/error为空。
- 模型14项、静态打包4项、前端构建及ruff通过；无新增依赖。已有大JS包构建提示保留。没有真实板卡验证或无障碍认证。

## 报告紧凑布局与默认折叠

- 文件/用例初始均折叠，切换运行重置；浏览器真实记录确认open=0。展开全部8组、折叠全部0组验证通过。
- 收紧批次元信息、状态栏、分组间距及配置行；仅显示非零状态计数。修正窄屏用例名称强制全宽导致的堆叠，组名/数量/色块同行。
- 实测桌面用例分组行34.6px、手机36.6px；390px屏根scrollWidth375。已查看case-report-compact-desktop.png和case-report-compact-mobile.png，折叠列表密度与展开配置的色块正常。
- 前端模型14项、静态4项及构建通过。

## Regression首版网页验收（2026-10-26）

- 新增/#regression，沿用浅色青绿、固定导航与紧凑表格；始终说明SDK/组件/模型为mock，真实CPU pytest非板卡实测。
- 浏览器提交单组件场景：28次实验，确认10-14→10-15，cmodel向前FAIL/回退PASS；查看原始exp_0003退出码1、堆栈与阶段证据，矩阵和报告正常。
- 浏览器提交非单调场景：严格模式确认更早的10-12→10-13，earliest_proven=true。从网页下载复现tar.gz，逐文件SHA256验证通过，独立目录pytest reproduce.py复现同一模拟断言失败。
- 已查看regression-workspace.png、regression-components.png、regression-mobile.png；桌面表单/摘要/矩阵层级清楚，手机390×844根scrollWidth375无根横向溢出，版本轨迹/表格内部横滚。控制台warn/error为空。
- 真实SDK、自由case输入、模型API、实际so加载及设备租约未接入；不把mock组件干预写成真实团队根因。

## Agent分组与回归页面设计落地（2026-10-27）

final result: passed

- 选定源：design/agent-regression-target.png（1487×1058）；实现：design/agent-regression-redesign-final.png。按用户新要求，一级回归导航改为Agent可展开分组，内含已启用回归定位及明确禁用/待接入的实验工作流、模型配置。既有项目继续编辑，未重建模板、未部署。
- 浏览器CSS1487×1058，原生截图1472×1047；QA组合图仅将实现截图等比近似归一至1487×1058（约1%密度差），并与源图拼接。已查看work/agent-ui-compare-full.png及hero/evidence聚焦对照；原始截图保留未缩放。
- 第一轮P2：好坏SDK日期换行、复现工具栏低于首屏。修复日期字号/不换行、组件说明行高、折叠栏与工具栏间距；重新捕获并对照。最终日期单行高29px，复现栏底部1046.9px，位于1058px视口内。
- 字体：保留系统中文字体/既有导航字号；正文与标题/版本/语义标签层级对应源图，搜索和对照文本适当增大。源图细微字形与渲染差异为P3，未声明逐像素复制。
- 间距与结构：结论带、五步进度、10版本轨迹、左右搜索/组件、折叠原始记录和复现工具栏对应选图；新增Agent层级属用户明确要求。
- 颜色/素材：浅底青绿色语义系统、红色失败/绿色通过、灰色未测；品牌图片复用现有素材，功能图标使用Tabler，无新增装饰图或手绘图标。
- 文案/数据：真实登记case为test_regression[fp16]，未伪造源图中的matmul；SDK日期/状态、搜索范围、组件干预与复现命令均来自服务记录。无回归样例只完成端点和报告步骤，日期/组件步骤保持未执行；尚无结论不伪装成功。
- 浏览器验证：Agent展开/收起不改变当前任务，回归入口有效；新建配置默认折叠，开始调查后自动收起；新建no_regression、运行中与最新通过状态正常；单组件边界10-14→10-15，矩阵向前FAIL/回退PASS；原始exp_0003日志可打开/关闭。复制摘要与完整重放命令已读回核对；Markdown下载成功。控制台warn/error为空。
- 手机390×844、根scrollWidth375。初次截图捕获到侧栏动画，复验sidebarRight=0后覆盖截图design/agent-regression-mobile-final.png，已打开检查；版本与表格内部滚动，日期无溢出，移动导航Agent入口有效。
- 前端16模型+4静态测试及构建通过，保留既有大bundle提示；未修改后端业务逻辑。修改未提交。剩余P3：系统字体细微差异；没有独立无障碍认证。

## 未连接时的回归流程演示修复（2026-10-27）

final result: passed

- 用户截图显示未连接页面只有鉴权入口，演示不可见；现改为直接显示完整预设样例，新增11阶段自动回放/暂停、单步前后和阶段选择。实际任务仍需连接，不绕过原API鉴权。
- 自动播放从阶段0到10完成；阶段选择4暂停、下一步进入5并出现10-14→10-15范围，示意记录与组件矩阵随阶段增加。默认完整样例28条，源码测试验证不存在提前组件归因。
- 所有浏览器日志/报告标注未执行pytest、未调用模型；没有实际耗时或真实SHA，复制可执行复现命令禁用，下载仅为演示JSON/报告。模型0次调用与2条示意决策分别呈现。
- 已刷新用户当前tab2，直接显示无需连接的演示控件及演示结果；最终截图design/regression-offline-demo-final.png已打开检查。390px手机根scrollWidth375、639px用户视口根scrollWidth628，无根横向溢出；修正中等宽度下日期列相互挤压。
- 前端17模型+4静态测试与构建通过，修改未提交。

## 2026-10-27 多用户数据库平台

- 本机真实PostgreSQL预览；姓名登录验收用户A，保存个人默认mock配置并本地验证，发起CPU no_regression调查成功。
- 切换B后任务/用量为空；再登录A恢复相同workspace、历史任务与个人配置。刷新恢复Cookie会话，旧用户延迟JSON响应由单独前端测试覆盖。
- 数据中心显示归属、任务日期、状态/结论色块；窄屏表格局部横滚，根页面无横向溢出。顶栏限制姓名宽度并保持单行。
- 模型页空态、新建、保存、mock测试及恢复历史均浏览器验证；没有输入真实Key、没有外部API调用；console error为空。
- 截图：design/platform-data-desktop.png、platform-models-desktop.png、platform-models-mobile.png。

## 2026-10-27 简约 UI 收敛

逐模块布局、信息取舍、token颜色与字体/间距规则见docs/UI_DESIGN.md；完整验收矩阵与本轮截图见docs/UI_REFINEMENT_QA.md。前端20项模型/会话测试+4项静态测试、生产构建通过。独立验收服务真实执行34参数配置/4 xdist workers与14实验组件回归；验证最新通过路径不出现空组件矩阵，390px下无根横向溢出，11轨道固定列和聚焦W键缩放仍可用。界面console error为空；未测试真实模型/板卡或完成完整无障碍认证。旧截图与新截图记录可能不同，不用于性能对比。

## 2026-10-27 Daily

独立localhost验收：月历有全PASS绿色与包含XFAIL等非全PASS红色，点击10-03进入32配置质量报告，FAIL筛选只返回1条；点击该case日志定位到对应数据库配置日志，明确历史为模拟内容。一键失败项复测真实执行2个CPU配置，保留原SDK/环境和原报告，结果FAIL+XPASS，原日期仍红且显示复测徽标。日历按实际月份需要显示4–6周，避免多余空白周；固定顶栏下用scroll-margin保持报告标题与日志面板可见。截图见frontend/design/daily/。真实SDK/板卡未测。

2026-10-27 Daily圆角日历：桌面独立16px圆角卡片、10px间距、PASS数量/耗时优先；移除格内重复状态和长说明。390px根宽375px，无横向溢出；手机收起次要标签，日期点击与报告返回正常。前端22+4项通过，生产构建通过。
