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
