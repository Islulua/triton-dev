# Blocked Layout 查看器

## 工具目的

入口：Tools → Blocked Layout（`/#tools-blocked`）。根据逻辑 tensor shape 与 Triton BlockedLayout，实时查看每个 CTA/block、warp、lane、线程所持有的元素，观察分布和连续性。纯浏览器计算，无需登录、板卡、编译器或服务端任务。

## 使用方法

左侧输入 shape（如 `8, 32`、`8x32` 或 `[8,32]`）和一份布局：

```mlir
#ttg.blocked<{
  sizePerThread = [1, 2],
  threadsPerWarp = [2, 16],
  warpsPerCTA = [2, 1],
  order = [1, 0],
  CGALayout = [[1, 0]]
}>
```

也接受 Gluon `gl.BlockedLayout([1,2], [2,16], [2,1], [1,0])`、对应 snake_case 具名参数或 JSON 对象；CGA 可用内联基向量或 `CTAsPerCGA / CTASplitNum / CTAOrder` 旧三参数。省略 CGA 表示一个 CTA。布局引用（例如 `CGALayout = #cga`）需要先替换为内联数组。

- 默认颜色区分 CTA，可切换 Warp / Thread 着色（首份归属）；格子大数字为行优先逻辑索引，小字 `Tn:Rm` 表示 CTA 内线程号及该线程的逻辑寄存器槽位。
- 悬停或键盘聚焦元素，高亮同一个 CTA、同一个线程持有的全部数据；底部显示坐标、CTA / W / L / T / R 和连续索引区间。
- 悬停或聚焦 CTA 图例，高亮该 block 的全部元素和索引区间。
- 同一元素被多个 lane、warp 或 CTA 持有时显示 `×N`，底部详情列出前8份归属及剩余数量；格子和线程高亮以首份归属为准，完整映射保留在计算模型中。
- 1维横排，2维矩阵，3–4维按后续维固定坐标分组；长图在固定视口内缩放/拖动平移。输入不合法时清空旧结果，避免把旧图误认为新布局。

## 注意事项

这是普通 BlockedLayout 的逻辑分布模型，并非运行 trace。shape 是一个布局所描述的逻辑 tensor shape，不能直接把整个 kernel 的输入尺寸代入并据此推断 launch grid。shape 超过基础 tile 时，通过增加每个线程持有的元素覆盖，**不会自动创建更多 CTA**；多个 CTA 必须由 CGA 明确描述。

`order[0]` 为最快变化维。先构造 register / lane / warp 位基，按 shapePerCTA 扩展或截断，再拼接 CGA；超出 shape 的 lane/warp/block 位表现为复制，零 register 位移除。`T = W × lanesPerWarp + L`。`R` 是逻辑槽位编号，不是编译器最终硬件寄存器号。

行优先逻辑索引使用 `((i0 × D1 + i1) × D2 + …)`，便于比较逻辑连续区间；不代表具体 kernel 的实际地址、stride、dtype 字节偏移、访存合并或 bank conflict。没有运行 kernel，也不验证目标设备是否支持所填 warp/CTA 配置。

支持1–4维、shape每维1–65536内的2的幂、最多65536个元素（基础布局参数每项仍不超过4096）、16个CTA、每warp128个lane、每CTA32个warp及262144条归属。非2的幂的实际输入可对应带mask的逻辑tile，但本工具不推断mask。Slice / MMA / swizzled / 自定义 LinearEncoding 暂不支持；任意代码不执行。

语义依据：

- [Triton BlockedLayout API](https://triton-lang.org/main/gluon/api/generated/triton.experimental.gluon.language.BlockedLayout.html)
- [Triton Tensor Layouts 教程](https://triton-lang.org/main/getting-started/tutorials/gluon/layouts.html)
- [上游 LinearLayoutConversions.cpp](https://github.com/triton-lang/triton/blob/main/lib/Dialect/TritonGPU/IR/LinearLayoutConversions.cpp)：`BlockedEncodingAttr::toLinearLayout` 与 `combineCtaCgaWithShape`。

已对照2026-11-04上游代码与官方32×8示例建立测试；不同SDK分支如果修改了布局规则，需要额外核对。

### 大图导航

分布图统一使用 Canvas，仅绘制当前视口可见的元素，不为每个元素创建DOM。大于256个元素时默认缩放到总览；计算上限为65536个元素与262144条归属，超限会报错。当前仍在浏览器中一次计算完整有界映射，尚未实现更大规模的分块聚合/按需计算。

- `Ctrl / ⌘ + 滚轮`：以鼠标所在位置缩放；普通滚轮保留页面滚动。
- 按住鼠标左键拖动或单指拖动：平移视口；拖动不会选中元素。
- 点击元素：固定该 CTA 内线程的所有数据高亮，再次点击同一元素、点“解除固定”或按Escape取消。
- `− / +`：以视口中心缩放；百分比复位100%；“总览”同时适应宽高，“适应宽度”只按横向范围调整。
- 聚焦画布后：`+ / -`缩放、`0`复位、方向键查看相邻逻辑元素并自动移入视口。详情通过屏幕阅读器可读。
- 缩放范围0.001%–400%。小格仅绘制色块，格宽达到32px显示索引，达到54px且格高39px显示线程/槽位及复制倍数；隐藏的文字始终可通过底部详情查看。

3–4维继续按后续维度分组，画布裁剪不可见分组；本轮没有增加轴选择、切片或框选控件。高密度总览可能将多个亚像素小格画在同一像素中，因此以放大后的格子和命中坐标为准，不能把总览颜色当作聚合统计。
