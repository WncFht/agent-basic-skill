# 消费方契约（consumer contract）

link-get 产物的下游消费面。字段名逐字对齐 connector 源码写法——改名即 breaking change。两套 meta.json **不统一 schema**（明确不做的项），消费方按 `platform`/文件名分别解析。

## canvas meta.json

每讲一份：`link-get <course-url> --lecture N -o DIR` → `DIR/meta.json`；`--all` 时每讲独立 `DIR/<cour_id>--<slug>/meta.json`（`scripts/connectors/canvas-get` 单处写法）。

| 字段            | 含义                                                                                |
| --------------- | ----------------------------------------------------------------------------------- |
| `platform`      | 常量 `"sjtu-canvas"`——辨识此 schema 的判别字段                                      |
| `course_id`     | Canvas 课程 id（oc.sjtu.edu.cn/courses/<id>）                                       |
| `tecl_id`       | 教学班 id（LTI launch-context 解析；play-center 链接为 AES 解出的 teclId）          |
| `lecture_index` | 本讲在讲次表的 1-based 序号（`--lecture N` 的 N）                                   |
| `cour_id`       | 讲次记录 id（讲次表行主键，子目录名前缀）                                           |
| `title`         | 讲次标题                                                                            |
| `begin` / `end` | 上课起止时间（源字段 `courBeginTime` / `courEndTime`）                              |
| `sources`       | `[{"viewNum", "kind"}]` 机位列表——viewNum 5/6 = PPT 录屏/电子白板，1-4/7 = 教室机位 |
| `lectures`      | `[{"index", "title"}]` 全讲次索引——增量比对新课程有没有新讲次靠它，不用重拉列表     |

同目录产物：`video.mp4`（多机位时另有 `camera<N>.mp4`）、`audio.wav`（16kHz 单声道）、`cover.jpg`。

## media-get meta.json

`link-get --media <url> -o DIR` → `DIR/meta.json`。**整条 yt-dlp `--dump-json` info dict 原文落盘**（`scripts/connectors/media-get` 取 stdout 首行 JSON），不是固定 schema——字段集随 yt-dlp 版本与 extractor 浮动。连接器自身消费的字段（这些被读，必然在）：

| 字段                 | 含义                                  |
| -------------------- | ------------------------------------- |
| `title`              | 标题                                  |
| `duration`           | 时长（秒）                            |
| `n_entries`          | 分 P / 播放列表条数（单视频缺省 = 1） |
| `subtitles`          | 人工 CC 字幕轨表（lang → 轨列表）     |
| `automatic_captions` | 自动字幕轨表                          |
| `thumbnail`          | 封面 URL                              |
| `height`             | 视频高度（ffprobe 缺席时的兜底）      |

下游常用、同属 yt-dlp 透传：`id`、`webpage_url`、`extractor`、`chapters`、`entries`（播放列表展开）、`formats`（全部格式表，挑清晰度先探它）。

同目录产物：`cover.jpg`、`video.mp4`、`<video>.<lang>.srt`（有 CC 轨时）、`audio.wav`（无 CC 轨时抽，喂 ASR）。

## xyzfm（小宇宙）meta.json

`link-get <episode-url|eid>` → `DIR/meta.json`。判别字段 `platform="xyzfm"` + `form`：`transcript`=官方转写束（xyzfm-tr 车道），`shownotes`=匿名面兜底束（xyzfm-sn 车道）——satisfies 断言靠 `form` 区分，消费方同样按它选文件。

episode 页公共字段（两 form 同 schema）：

| 字段                  | 含义                                                             |
| --------------------- | ---------------------------------------------------------------- |
| `platform`            | 常量 `"xyzfm"`                                                   |
| `form`                | `"transcript"` / `"shownotes"`——satisfies 断言键与产物判别字段   |
| `eid` / `pid`         | 集 id / 节目 id                                                  |
| `title`               | 集标题                                                           |
| `podcast_title`       | 节目名                                                           |
| `duration_s`          | 时长（秒）                                                       |
| `pub_date`            | 发布时间（源字段 `pubDate`）                                     |
| `url`                 | 集页规范 URL                                                     |
| `audio_url`           | 音频 enclosure（RSS 源直链）                                     |
| `transcript_media_id` | 转写键（`transcriptMediaId` 优先，media.id/mediaKey 兜底；可空） |

`form="transcript"` 追加字段：`transcript_vendor`（`vendorDeclaration`，转写供应商声明）、`transcript_key`（转写 CDN key）、`transcript_segments`（段数）。

同目录产物（按 form）：`transcript.txt`（`[MM:SS] text` 行，无说话人标签——仅 transcript 束）、`shownotes.md`（节目 shownotes HTML → 轻量 md，两束都落）。

podcast 页（`link-get <podcast-url>`，art 臂）是**缩减 schema**：`platform` / `form="shownotes"` / `pid` / `title` / `url` / `episode_count`——无 eid/duration 等集级字段。产物 `article.md`（简介+前 50 集链接表）+ `meta.json`。
