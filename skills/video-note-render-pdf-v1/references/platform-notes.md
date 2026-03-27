# Platform Notes

统一 `video-note-render-pdf-v1` wrapper 仍然需要保留平台特有边界。平台差异不应该重新长回两个平行 skill，但也不能完全消失在 adapter 实现里。

## YouTube

- 优先使用公开视频直接可得的官方字幕。
- 手工字幕优先于自动字幕。
- 若公开视频已经能匿名拿到字幕，不要先要求 cookies。
- 如果公开视频只有自动字幕，也要先把 manual / auto 区分写进 probe 结果，再决定是否接受。

## Bilibili

### 分 P 处理

- 分 P 视频必须先识别完整 part 列表。
- 在真正下载或写正文前，先明确本次要处理哪些 part。
- 如果用户没有指定范围，先停在“确认 part selection”而不是默认把所有 part 混成一个 case。
- 推荐把选择结果写进 `case_manifest.json.runtime.part_selection`。

### URL 归一化

- 需要支持标准 `bilibili.com/video/BV...` 链接。
- 也需要支持 `b23.tv` 短链，并在 case metadata 中保留归一化后的标准 URL。

### 字幕与 cookies

- 仍然先尝试平台官方字幕，再尝试 cookies 路径，最后才进入 ASR。
- Bilibili 的 1080P+ 与某些字幕/媒体路径可能依赖 cookies，但 cookies 不应取代 subtitle-first 的顺序。
- 若最终走了 cookies 路径，必须在 probe 或 manifest 中记录“使用了 cookies”。

### Danmaku 不可作为教学内容源

- danmaku 噪声很高，不能作为正文事实来源。
- 弹幕可以帮助人工判断“这里可能有高互动片段”，但不能替代官方字幕、ASR transcript 或画面证据。
- 如果正文确实引用了 danmaku 提到的现象，也必须回到画面、字幕或讲者原话做二次确认。

### Visual-only 末端 fallback

当以下条件同时出现或任意一个足以破坏 transcript 可信度时，可以转入 `visual-only` 思维模式：

- 平台字幕与 cookies 字幕都失败
- ASR 不可用，或 sample probe / 实际结果明显不可接受
- 视频的教学信息主要存在于幻灯片、白板、代码界面或图表，而音频文本本身价值很低

进入 `visual-only` 并不意味着“无约束自由发挥”，而是：

- 更依赖 overview、montage、高召回候选帧和必要的重绘
- 必须显式记录为什么没有使用可接受的 transcript
- 推荐把原因写进 `case_manifest.json.runtime.visual_only_reason`

## 不该做的事

- 因为统一 skill 只有一个入口，就默认平台差异已经不重要
- 在分 P 视频里没确认范围就直接开始抓素材
- 把 danmaku 当作教学内容主来源
- 还没判断 transcript 是否可信，就直接按字幕写正文
