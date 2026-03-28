# Coverage And Revision Guidance v2

这份文档聚焦两个问题：

- 讲义主体篇幅如何和视频中的内容强度同向扩张
- 完稿后如何做真正有内容价值的 revision，而不是只重复 build

## 字数 Guardrail 先于页数目标

v2 默认不再把页数当成长度目标。更合理的目标是：

- 主体正文总长度应和视频整体字幕量、主题复杂度、讲解时长大致正相关
- 各主要段落在讲义中的篇幅占比，应尽量接近它们在视频中的相对权重
- 长视频和中长视频宁可略长，不要明显偏短

正式写正文前，先根据 `transcript.txt` 算：

- `transcript_txt_chars`
- `min_note_chars`
- `soft_note_char_range`
- `compression_ratio`

默认用下面这张分段启发式表：

| 字幕字数 `S` | 建议保底下限 | 常见舒适区 |
| --- | --- | --- |
| `S < 5000` | 至少 `6000` 字 | `6000 ~ 12000` 字 |
| `5000 <= S < 15000` | 至少 `0.55S` | `0.55S ~ 1.00S` |
| `15000 <= S < 35000` | 至少 `0.40S` | `0.40S ~ 0.70S` |
| `35000 <= S < 70000` | 至少 `0.30S` | `0.30S ~ 0.55S` |
| `S >= 70000` | 至少 `0.18S` | `0.18S ~ 0.35S` |

执行约束：

- 先把这四个字段写进 `work/section_alignment.json`
- 若最终 `note.tex` 低于 `min_note_chars`，必须再做一次 coverage pass
- 若最终字数高于软范围，只要新增内容确有价值，一般可以接受
- evaluator 后续会把这张表转成单调校准曲线；wrapper 执行时先按这张表即可

## Lightweight Content Map

正式写正文前，先做一个轻量 content map。它不需要很重，但至少应回答：

- 主体内容可以拆成哪几个时间段或主题段
- 哪几段是正文主力
- 哪几段可以适度压缩
- 哪几段需要绑定关键图、公式、代码或外部证据
- 哪些段落容易跌破 `min_note_chars` 约束

对于短视频，这可以只是写作前的内部思考。
对于长视频、高字幕量或 evidence-heavy case，建议把它落成轻量 artifact，例如：

- `work/section_alignment.json`
- `review/coverage-note.md`

## 什么时候判定 coverage 不足

以下情况通常值得回头扩写：

- 长视频主体只写成固定厚度的 1 份中等篇幅讲义
- 视频中的重点段在讲义里只占 1 个很短的小节
- 大量正文预算被前言、背景或总结吃掉，主体解释反而偏短
- 长段口头论证被压成结论列表，失去原本的推理过程
- 最终 `note.tex` 字数低于 `min_note_chars`

以下情况通常可以接受压缩：

- 明显重复的例子
- 纯礼貌性或频道运营性内容
- 对后文没有贡献的闲聊

## 三段式 Revision Loop

### 1. Coverage Pass

重新对照 transcript、content map 和 guardrail，检查：

- 哪些视频里的重点段在讲义里被压缩得过短
- 哪些章节写得明显过厚，和视频里的实际比重不匹配
- 是否有应该保留到主体章节的内容，被错误地塞进总结或被完全漏掉
- 当前字数是否仍低于 `min_note_chars`

### 2. Figure Pass

逐图复查：

- 这张图属于 `evidence`、`explanation`、`demo-pair`、`anchor-pair` 还是 `orientation`
- 没有这张图，正文是否会明显变差
- 它是否已经是当前条件下最清楚、最完整、最合适的版本
- 是否更应该改成外部原件、pair、derived figure 或直接删除
- `visual_obligation_ledger` 中对应项是否已经被兑现或豁免

建议把结果落成：

- `review/figure-audit.md`

### 3. Page Pass

结合 `pdf_preview/` 或最终 PDF 页面检查：

- 图是否进入页面后仍然清晰可读
- 脚注、时间区间和 caption 是否稳定
- 某页是否突然过密、过空或图文失衡
- 是否存在一页里堆了太多盒子或太多小图

建议把结果落成：

- `review/page-flags.md`

## Revision Action Log

review 不再是终点，而是触发器。对长视频、高字幕量、evidence-heavy 或高视觉义务 case，默认再保留：

- `review/revision-actions.json`

每条动作至少包含：

- `issue_id`
- `issue_type`
- `severity`
- `evidence_path`
- `action_taken`
- `touched_files`

推荐 `action_taken`：

- `layout-fix`
- `provenance-fix`
- `content-expand`
- `content-trim`
- `figure-swap`
- `figure-waive`
- `no-action`

## 什么情况下不能声称 revision 完成

以下任一情况成立时，都不能说 revision loop 已完成：

- `review/coverage-note.md` 或 `review/figure-audit.md` 里写出中等以上问题，但 `note.tex` 没有更新
- 只补了 review 文件，没有对应 action log
- 只是再次 build，没有 coverage / figure / page 的实质回写
- 最终成稿仍低于 `min_note_chars`，但没有明确解释为何允许豁免

## 不该做的事

- 把重复 build 当成已经做过 revision
- 把固定页数配额当成 coverage 正确
- 只因为“有图”就保留一张实际阅读价值很低的截图
- 因为想省时间而跳过对字幕重点段和关键图片的最后一次回读
- 写了 review 但没有把动作落到 `note.tex`、图片资源或 action log 上
