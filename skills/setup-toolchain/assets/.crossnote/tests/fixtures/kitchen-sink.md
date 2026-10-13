---
# =============================================================================
# kitchen-sink.md — .crossnote (MPE 预览主题) 人工验收夹具
#
# 用途：单文件集齐 style.less 覆盖的全部 Markdown 元素。在 VS Code 里打开
#       MPE 预览，用右下角悬浮按钮逐个切换 8 个主题槽位（跟随系统 / 跟随编辑器 /
#       暖纸 / 羊皮纸 / 雪白 / 暖黑 / One Dark / 纯黑），目检颜色对比度、边框、
#       行距、字体与代码语法高亮是否协调。本文件不进 node --test 套件。
#
# ⚠ 预览环境要求：runtime 注入只在 projectDir 有 .crossnote 农场时生效——
#       请从「以 ~/.agents 为根的窗口」预览本文件（projectDir=~/.agents，
#       农场已挂）。在别的仓库窗口里打开本文件时 projectDir 退化为文件所在
#       目录（tests/fixtures，无农场），结果是降级预览：主题照常（全局层
#       style.less 兜底），但没有外观按钮、pseudocode 围栏按源码块渲染。
#       这是设计行为，不是故障。
#
# class 属性示例（完整清单见 style.less 文件头注释）：
#   class: "serif"                正文西文字体：sans / serif / mono
#   class: "fs16px"               字号：fs12px .. fs18px
#   class: "colorhead headnum-h2" 彩色标题 + 自 H2 起编号，可叠加
#   class: "wrapcode"             代码块长行折行
#   class: "dense-table"          表格变体：simple / xline / yline /
#                                 xyline / noline / nohead / dense
class: "serif"
---

# Kitchen Sink 主题验收页

> 本文件是 .crossnote（Markdown Preview Enhanced）预览主题的人工验收夹具。
> 逐节核对每个元素在当前主题槽位下的渲染；验收时先过一遍默认「暖纸」，
> 再切换「暖黑 / One Dark / 纯黑」检查暗色槽位。

正文首段：中文与 English 混排，行内 `code`，外加一个超长的行内代码
`https://example.com/api/v1/namespaces/some-namespace/resources/0123456789abcdef?pretty=true&fields=metadata.name,spec.template,status.conditions#section-2`
观察是否撑出横向滚动或异常折行。脚注引用见[^a]与[^b]，定义在文末。

## 标题层级

H1 在文件顶部，下面逐级下钻到 H6，核对彩色标题与字重梯度。

### 三级标题

#### 四级标题

##### 五级标题

###### 六级标题

## 行内样式

粗体 **bold**、斜体 _italic_、删除线 ~~strikethrough~~、高亮 ==mark==；
上标 x^2^ 与下标 H<sub>2</sub>O（`~sub~` 写法会被 formatter 归一成
strikethrough，下标一律走 HTML），另有 <sup>sup</sup> / <sub>sub</sub> 标签；
键盘键位 <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>P</kbd>。

CriticMarkup：这句包含 {++新增的文本++} 与 {--删除的文本--} 两处批注。

链接：[Markdown 链接](https://example.com "title") 与裸链 https://example.com。

## 列表

无序列表：

- 一级项目甲
- 一级项目乙
    - 嵌套项目乙一（MD007:4 空格缩进）
    - 嵌套项目乙二
- 一级项目丙

有序列表：

1. 第一步
2. 第二步
    1. 嵌套步骤
    2. 再嵌套
3. 第三步

任务列表：

- [ ] 未完成任务
- [x] 已完成任务
- [ ] 带 ==高亮== 与 `code` 的任务

## 表格

核对表头底色、内部边框与超长单元格折行：

| 主题槽位   | 背景      | 前景      | 派生变量                                                   | 验收要点                                                                                                 |
| ---------- | --------- | --------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 暖纸 paper | `#f5f1e8` | `#211b12` | `--bg` `--text` `--border` `--table-header-bg` `--code-bg` | 默认 `:root` 槽位；本列故意写得足够长，验证单元格在表格固定宽度下正常折行而不撑破布局                    |
| 暖黑 dark  | `#17130e` | `#e8e0d0` | 同上                                                       | 跟随系统暗色时经 `system-dark` 委托至此；注意 callout 文字亮度补偿 `--callout-text-shift` 与斑马纹可读性 |
| One Dark   | `#282c34` | `#abb2bf` | 同上                                                       | 冷色对照组：检查代码语法高亮与背景、边框的融合度                                                         |

## 围栏代码块

长行 Python 块：先看默认横向滚动，再开 `wrapcode` 对比折行。

```python
"""Deliberately long-lined python fixture for horizontal scroll checks."""

import hashlib
import mimetypes
from pathlib import Path


def build_manifest(root, *, strict=False):
    root = Path(root)
    return [
        {"name": p.name, "relpath": str(p.relative_to(root)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size, "mime": mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink() and (not strict or p.stat().st_size > 0)
    ]


def render_report(manifest, output_path):
    lines = [f"{row['sha256'][:16]}  {row['bytes']:>12,d}  {row['mime']:<48}  {row['relpath']}" for row in manifest]
    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
```

## 伪代码

```pseudocode
\begin{algorithm}
\caption{RunningMean\\{\small\textit{Semantics: 根据正文重构}}}
\begin{algorithmic}
\INPUT new observation $x_t$; running mean $\bar{x}_{t-1}$; count $t \ge 1$
\OUTPUT updated mean $\bar{x}_t$
\STATE $\bar{x}_t \gets \bar{x}_{t-1} + \frac{x_t - \bar{x}_{t-1}}{t}$
    \COMMENT{Welford 递推，数值稳定}
\RETURN $\bar{x}_t$
\end{algorithmic}
\end{algorithm}
```

伪代码块应渲染为带 caption 的 figure，行内数学走 KaTeX。

## 行间公式

超长 align 环境，核对 KaTeX 渲染与横向溢出表现：

$$
\begin{aligned}
\mathcal{L}_{\mathrm{total}}(\theta)
    &= \underbrace{\mathbb{E}_{(x,\, y) \sim \mathcal{D}}\!\left[\ell\bigl(f_{\theta}(x),\, y\bigr)\right]}_{\text{经验风险}}
        + \lambda_{1} \underbrace{\sum_{l = 1}^{L} \left\lVert W^{(l)} \right\rVert_{F}^{2}}_{\text{权重衰减}}
        + \lambda_{2} \underbrace{\operatorname{KL}\!\left( p_{\theta} \,\middle\Vert\, q_{\mathrm{ref}} \right)}_{\text{蒸馏正则}} \\
    &\quad + \lambda_{3} \sum_{t = 1}^{T} \mathbb{E}_{z_{t} \sim \pi_{\theta}(\cdot \mid s_{t})}\!\left[ \log \frac{\pi_{\theta}(z_{t} \mid s_{t})}{\pi_{\mathrm{ref}}(z_{t} \mid s_{t})} \cdot \hat{A}_{t} \right]
        - \beta \sum_{k = 1}^{K} p_{\theta}(k \mid x) \log p_{\theta}(k \mid x) \\
    &\quad + \gamma \left\lVert \nabla_{\theta}\, \mathcal{L}_{\mathrm{total}}(\theta) \right\rVert_{2}^{2}
        + \eta \sum_{i < j} \max\!\bigl(0,\; m - d\bigl(f_{\theta}(x_{i}),\, f_{\theta}(x_{j})\bigr)\bigr) \\
    &\quad + \rho \sum_{v \in \mathcal{V}} \phi\!\left( \sum_{u \in \mathcal{N}(v)} \alpha_{u v}\, W h_{u} \right)
        - \tau \log \sigma\!\left( w_{v}^{\top} w_{v'} \right) \\
    &\quad + \kappa \sum_{(v,\, v') \in \mathcal{E}^{+} \cup \mathcal{E}^{-}} \omega_{v v'} \cdot \psi\!\left( h_{v},\, h_{v'};\, \theta \right)
\end{aligned}
$$

## Callout 提示块

<!-- 相邻 callout 之间用注释行隔开：纯空行会被 MD028 判成同一块引用 -->

> [!note] 笔记 Note
> note callout：蓝色系、`edit` 图标。支持多段落。
>
> 第二段，含 `code` 与 **加粗**。

<!-- -->

> [!warning] 警告 Warning
> warning callout：黄色系、`warning` 图标。长文本折行检查——这一段故意写长一点，看看左边框、内边距与正文基线在换行后是否仍然对齐。

<!-- -->

> [!abstract] 摘要 Abstract
> abstract callout：蓝色系、`subject` 图标（`.summary` / `.tldr` 同族）。

<!-- -->

> [!quote] 引文 Quote
> quote callout：中性灰、`format_quote` 图标，文字色走 `--text-muted`。

<!-- -->

> [!tip]- 折叠提示（默认收起）
> tip callout 折叠版：`[!tip]-` 应渲染为可点击展开、初始收起的块；
> 展开后这段正文可见，绿色系、`lightbulb` 图标。

## 嵌套引用与分割线

> 外层引用第一层。
>
> > 内层嵌套引用：核对缩进阶梯与左边框层次。
>
> 回到外层引用。

---

分割线上方是嵌套引用，下方是折叠块与图片。

## 折叠块与图片

<details>
<summary>details + summary 折叠块（点击展开）</summary>

折叠体内的 Markdown 应正常渲染：

- 列表项
- `code`、**加粗** 与 ==高亮==

</details>

图片占位（`assets/demo.png` 不存在，检查 broken-image 与 `centerimg` 表现）：

![x](assets/demo.png)

## 脚注定义

正文引用的两条脚注在文末定义，点击预览里的角标应跳转到这里。

[^a]: 第一条脚注：含行内 `code` 与 [链接](https://example.com)。

[^b]: 第二条脚注：纯文本，验证返回引用箭头的跳转。
