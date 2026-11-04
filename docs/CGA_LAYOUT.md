# Tools / CGA Layout

2026-11-04。入口 `/#tools` → CGA Layout，直接入口 `/#tools-cga`。

## 使用

页面只保留一个布局输入框与一个CTA tile展示框。粘贴布局后实时更新，无需提交。支持裸基向量、单份MLIR/Gluon布局片段与旧三参数格式：

```text
[[0, 1], [1, 0]]
```

```text
CGALayout = [[0, 1], [1, 0]]
```

```text
CTAsPerCGA = [4, 2]
CTASplitNum = [2, 2]
CTAOrder = [0, 1]
```

每格显示逻辑tile坐标与拥有它的CTA编号；相同tile的CTA合并到一格。高维布局在同一展示框内按D2/D3固定坐标自动分组，1D按一行展示。长图仅展示框内部滚动。输入错误时不显示旧结果，错误直接在展示框提示。

空基向量 `[]` 默认为二维单CTA；需要其他空布局维数时可在同一输入框中写 `{"bases":[],"rank":3}`。非空基向量自动识别维数。

不提供预设、统计、切片控件、CTA选择/详情、tile shape、导出或分享。独立本地计算，无需登录、编译或设备，输入不执行Python/MLIR代码。

## 映射语义与边界

CTA编号从低到高的二进制位依次选择基向量，tile坐标为选中向量按位XOR。零基表示数据复制。例如 `[[1,0],[0,0],[0,1]]` 中8个CTA对应4个独立tile，CTA1与3同为 `[1,0]`。

旧格式按CTAOrder最快维在前，逐维先生成split的identity基，再插入total/split的零基；复制位可能在中间，不能简单将全局CTA编号取模。

支持1–4维、最多8个基/256 CTA；这只是展示上限，不是硬件cluster合法性证明。非零基必须只含一个2的幂分量，输出位不重复且连续。拒绝任意LinearEncoding耦合、缺位或重复非零基。输入限制16384字符，单份布局。

只展示逻辑tile，不推断SM物理布置、warp/lane、实际内存地址或真实tensor元素范围。每格复制编号过多时显示前8个和剩余数量，悬停可查看全部编号。

## 实现

`frontend/src/tools/cga-layout.js`为纯解析/映射模块，`tools/CgaLayoutTool.jsx`只管理单输入和排列展示；Tools集合与独立子路由由`ToolsWorkspace.jsx`登记。

依据（核对日期2026-11-04）：[Triton Multi-CTA](https://triton-lang.org/main/getting-started/tutorials/gluon/multicta.html)、[CGAEncodingAttr校验与fromSplitParams](https://github.com/triton-lang/triton/blob/main/lib/Dialect/TritonGPU/IR/Dialect.cpp)。
