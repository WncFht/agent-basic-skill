# Adapter Contract

统一视频讲义 pipeline 的 adapter 层负责把 YouTube / Bilibili 的差异吸收掉，再向下游输出统一事实层 artifact。

## Adapter 最低职责

- 识别平台与标准化 URL
- 提取 `video_id`、标题、作者、时长、分段信息，并在需要时支持短链归一化
- 探测字幕候选，区分 manual / auto / language / anonymous / cookies
- 探测可下载格式与封面图
- 在平台字幕失败后触发 ASR probe，不直接跳过到正文生成

## `preflight.json`

至少包含：

```json
{
  "platform": "bilibili",
  "video_id": "BVxxxx",
  "title": "",
  "duration_seconds": 0,
  "cover_url": "",
  "parts": [],
  "chapters": [],
  "recommended_mode": "talking-head",
  "video_probe": {
    "best_downloadable_format": "",
    "requires_cookies_for_hd": false
  }
}
```

## `subtitle_probe.json`

至少包含：

```json
{
  "platform": "youtube",
  "video_id": "",
  "anonymous": {
    "ok": true,
    "tracks": []
  },
  "cookies": {
    "ok": false,
    "tracks": []
  },
  "selected_track": {
    "source": "official-anonymous",
    "language": "zh-Hans",
    "kind": "manual"
  }
}
```

要求：

- `source` 只能是 `official-anonymous`、`official-cookies` 或 `none`
- 若 `selected_track` 为空，必须显式说明失败原因
- 若最终需要转入 `visual-only`，失败原因必须足以解释为什么没有可接受的字幕路径

## `transcriber_probe.json`

仅在平台字幕链路失败时进入。至少包含：

```json
{
  "required": true,
  "backend_candidates": [
    {
      "name": "faster-whisper",
      "device": "cuda",
      "sample_ok": true
    }
  ],
  "selected_backend": "faster-whisper"
}
```

要求：

- 先 probe，再真正跑长任务
- 记录 device、compute type、sample success 与失败原因
- 不把单一 backend 写死为唯一实现

## Transcript 输出

不论来源是平台字幕还是 ASR，最终都要统一输出：

- `transcript.json`
- `transcript.srt`
- `transcript.txt`

`transcript.json` 至少包含带时间戳的片段数组，便于后续按时间窗选图。

如果某个 case 最终采用 `visual-only` 思维模式，adapter 或上层 manifest 仍必须显式记录：

- 为什么平台字幕不可用或不可接受
- 为什么 ASR 不可用、失败或质量不足
- 当前 case 为什么可以不依赖 transcript 进入后续写作
