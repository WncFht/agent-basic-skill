---
name: link-get
description: 任意链接或裸 ID → 文本内容（Markdown / SRT / TeX 源）的统一入口。当用户粘贴 YouTube、Bilibili（视频/动态 opus）、知乎、微信公众号、SJTU Canvas、arXiv abs 页、小宇宙（xiaoyuzhoufm）episode/podcast 链接或任意网页链接，要求"看看这个链接讲了什么"、抓正文、提字幕/文字稿、取论文 LaTeX 源时使用；也吃裸形态——arXiv 新/旧式 ID（2303.08774、math.AG/0601234）与 arxiv:<id> 直出 TeX 源，SJTU 裸课程号进 Canvas，小宇宙裸 24 位 eid 出官方文字稿，无 scheme 的 host/path 自动补 https。--media 直接落盘视频/音频。按域名分发：YouTube 走 yt-dlp + transcript-api，Bilibili 走 yt-dlp + BBDown 兜底，知乎委派 zhihu-get，Canvas 委派 canvas-get，arXiv 委派 arxiv-tex（uvx arxiv-to-prompt 版本戳 wrapper），小宇宙走私有 API 官方转写 → shownotes 兜底（--mint 扫码铸 token），微信走 defuddle→tavily→firecrawl，通用文章走 defuddle→trafilatura→jina→firecrawl。
---

# link-get

`link-get <url|id> [-o DIR] [--fast] [--media]` — 只解决"这链接里写了什么"（文本层）。
要视频本体 → `--media`（落盘 video.mp4 + audio.wav，喂 video-render-pdf / asr）。

输入形态：完整 http(s) URL；无 scheme 的裸 host/path（`zhihu.com/p/1` 自补 https）；arXiv 新式 `2303.08774`、旧式 `math.AG/0601234`、`arxiv:<id>` → TeX/LaTeX 源；SJTU 裸课程号（`\d{4,6}` → oc.sjtu.edu.cn 课程页）。其余裸 token 无 pack 认领 → rc3。

## 路由

link-get 本身只做分发；每条车道是 `scripts/connectors/` 下的独立 CLI。connector 裸跑只是 debug 通道（无 admit 闸 / journal / 预算约束）——生产入口唯 `link-get`（恒经 fetch-engine）。

<!-- pack-table:start -->

<!-- prettier-ignore-start -->

| URL | 连接器 / 车道 |
| --- | --- |
| `arxiv.org`、`*.arxiv.org`、`export.arxiv.org` | `arxiv-tex`：arXiv → TeX/LaTeX 源（arxiv-tex = uvx arxiv-to-prompt 的 lgc 版本戳 wrapper） |
| `bilibili.com`、`*.bilibili.com`、`b23.tv`、`*.b23.tv` | `bilibili`：元数据 + 字幕（`all,-danmaku`）→ BBDown AI 字幕兜底；`/opus`、`t.*` 走 polymer API → md；`--mint` 重铸 bili 凭证 |
| `oc.sjtu.edu.cn`、`*.oc.sjtu.edu.cn`、`v.sjtu.edu.cn`、`*.v.sjtu.edu.cn` | `canvas`：PAT 直通 REST + LTI 实录；枚举走 canvas-rest，`--mint` 铸 cred，`--download` 直连 |
| `mp.weixin.qq.com` | `wechat-get`：defuddle → tvly-hikari → firecrawl |
| `xiaoyuzhoufm.com`、`*.xiaoyuzhoufm.com` | `xyzfm`：小宇宙：官方文字稿（带时间戳，需 token）→ shownotes 匿名兜底；--mint 扫码铸凭证 |
| `youtube.com`、`*.youtube.com`、`youtu.be`、`*.youtu.be` | `youtube-get`：yt-dlp -J → transcript-api 时间戳转录 → yt-dlp 字幕；`--fast` 走 defuddle |
| `zhihu.com`、`www.zhihu.com`、`*.zhihu.com`、`zhuanlan.zhihu.com` | `zhihu`：按 URL 形态定 kind → 车道级联：tardis 免登录镜像 → zhcli → scraper → jina → firecrawl |
| 其他 http(s) | `generic`：defuddle → trafilatura → jina → firecrawl；doc 臂 → MinerU 云解析 |
| `--media` | `media-get`：meta.json + cover + video.mp4 + srt / audio.wav |

<!-- prettier-ignore-end -->

<!-- pack-table:end -->

## fetch-engine 分发

`link-get <url> [flags]` 恒经 `scripts/fetch-engine` 分发（Phase-5d 起唯一路径）——packs/ 声明式路由 + 每任务 journal（`~/.cache/link-get/jobs/<job>/journal.jsonl`）+ admit 闸（SSRF/冷却/预算）。旗标自动翻译为 engine `--param`（带值旗标→`k=v`，`--fast`/`--comments`→flag 参数 + zhihu 变体键/`variant`）。

不经 engine 的旁路：`--mc`（知乎 MediaCrawler 搜索/枚举，非知乎目标带 `--mc` 拒 rc2）→ zhihu-get；canvas `--download`（签名链新鲜性契约）→ canvas-get。canvas 枚举类（`--list-courses`/`--files`/`--announcements`/`--assignments`/`--mint`）走 engine `kind=enum` 数据道。`--token` 走 `CANVAS_TOKEN` env 透传，不进 argv/journal。

pack 清单在 `packs/*/pack.toml`；lane 协议与 journal 格式见 `references/lane-abi.md`。

## Canvas（SJTU）

`link-get <课程url|裸课程号|play-center 链接>`——一个 PAT 打通 REST 与 LTI 实录。Token 优先级：`--token` > `$CANVAS_TOKEN` > `~/.config/canvas-skill/token`（chmod 600；Canvas「设置 → 批准集成 → 新访问令牌」生成）。

| 命令                                                   | 作用                                                                                             |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `link-get --list-courses`                              | 列在选课程（id + 名称）                                                                          |
| `link-get <url\|id> --files`                           | 列课程文件                                                                                       |
| `link-get <url\|id> --files --download DIR`            | 批量下载文件——签名链新鲜性契约，直连 canvas-get 旁路（不经 engine）                              |
| `link-get <url\|id> --announcements` / `--assignments` | 公告 / 作业 + 截止时间                                                                           |
| `link-get <course-url>`                                | 列讲次（带 cour_id、[已下载]/[已缓存]/[不可点播] 标记——[已缓存]=束在 lgc，删了 -o 目录也能秒回） |
| `link-get <course-url> --lecture N [-o DIR]`           | 下第 N 讲 → video.mp4 + audio.wav + cover.jpg + meta.json                                        |
| `link-get <url> --all` / `--camera all\|N`             | 全部讲次 / 指定机位（auto 默认挑 viewNum 5/6 = PPT 录屏/电子白板）                               |
| `link-get <play-center-url> --lecture N`               | 分享链接（本地 AES 解 teclId，借 donor 课 token）                                                |
| `link-get <url\|id> --mint`                            | 铸 LTI cred 键（jwt 20min + tecl 180d 入 lgc，jwt 不打印）                                       |

`--cover-at` 默认 120s——课前多为签到画面，对准第一页标题 slide；audio.wav 16kHz 单声道直接喂 asr；meta.json 带全部讲次索引供增量比对（schema 见 `references/consumer-contract.md`）。LTI 链路细节见 `references/canvas-lti.md`。

## 知乎

URL 形态 → kind → 车道级联见上表与 `packs/zhihu/pack.toml`：

| URL 形态                                           | kind           | 级联（首中胜）                                                                        |
| -------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------- |
| `/p/<id>` 文章                                     | art            | zhcli → tardis → jina → firecrawl；`--fast` → tardis → jina                           |
| `/question/q/answer/a` 回答                        | ans            | tardis → scraper → jina → firecrawl；`--fast` → tardis → jina；`--comments` → scraper |
| `/question/q` 问题                                 | q              | zhcli → jina → firecrawl；`--fast` → jina                                             |
| `/column/<slug>`、`zhuanlan.zhihu.com/<slug>` 专栏 | col            | scraper                                                                               |
| `/people/`、`/zvideo/`、`/pin/`                    | ppl / zv / pin | zhcli                                                                                 |

- 评论全树 / 批量 / 搜索 / 用户作品枚举：`link-get --mc detail|search|creator <args>`（MediaCrawler，旁路 zhihu-get 不经 engine；非知乎目标带 `--mc` 拒 rc2）。
- 匿名面/z_c0 需求矩阵/各工具边界：`packs/zhihu/references/routing.md`；cookie 取法与 `auth-zhihu.sh`：`packs/zhihu/references/cookie.md`；风控与已知坑：`packs/zhihu/references/pitfalls.md`。
- 收藏夹无路由——备选 JasonJarvan/Zhihu-Collections-MCP（公开免 cookie），需另装。

## arXiv

`link-get <id|abs/pdf URL>` → LaTeX 源（arxiv-to-prompt，公式/章节/图表引用精确——读论文首选，优于 PDF→pdftotext）。`--mode abstract|list|sections|figures|tokens` 取局部（空格形与 `=` 形皆可；`sections` 须配 `--section <节名>`，逗号分隔多节）；`--no-comments`/`--no-appendix`/`--expand-macros` 修饰输出。PDF-only 论文无 TeX 源 → rc3 回退 generic/PDF 解析。墓碑语义：内容级不覆盖记 30d，参数级拒绝（scope_hint=params）不记账。

## 小宇宙（xyzfm）

`link-get <episode URL|裸 24 位 eid>` → 官方文字稿 `transcript.txt`（`[MM:SS]` 时间戳，无说话人标签）+ `shownotes.md` + `meta.json`。转写走私有 API——凭证在 `~/.config/xyzfm/token.json`（access+refresh+device_id，chmod 600）。

| 命令                              | 作用                                                                    |
| --------------------------------- | ----------------------------------------------------------------------- |
| `link-get <url\|eid>`             | 官方转写三件产物；token 缺席/失效自动降级 shownotes                     |
| `link-get <url\|eid> --mint`      | 铸/修凭证：refresh 快速道优先，失败转 QR（PNG+终端码），小宇宙 App 扫码 |
| `link-get <url> --param kind=art` | 只要 shownotes（匿名面）                                                |
| `link-get <podcast URL>`          | 节目简介+集表（art 臂）                                                 |

降级语义：tr 臂 `[xyzfm-tr → xyzfm-sn]` 级联——`auth_expired` 让位 shownotes 兜底而非硬挂；兜底束记 `form=shownotes` 与 satisfies 断言互锁，`--mint` 后重试自动转正（mint 顺手清 auth lane 账）。该集本身无转写 → `notcovered`（lane×key 30d，重试直接供 shownotes）。无转写又可转写的少数集 → `--media` + asr 管线。TTL：`xyzfm:tr` 30d、`xyzfm:art` 7d。

## 凭证层

- `refresh-cookies`（= `scripts/refresh-cookies.sh`）：从 fht-mba Chrome 抓 zhihu/bilibili 登录态；keychain 口令在 `~/.config/link-get/mac-keychain.pw`（chmod 600）。
- B 站 cookie 落 `~/.config/link-get/cookies/bilibili.txt`（yt-dlp 全局 config 引用），并生成 `~/BBDown.data`。
- Canvas 不走 cookie——PAT 在 `~/.config/canvas-skill/token`。
- 小宇宙不走 cookie——access+refresh+device_id 在 `~/.config/xyzfm/token.json`（chmod 600）；`--mint` refresh 换新或扫码重铸。
- zhihu-cli（`zhihu`）`auth` 重写 `~/.zhihu-cli/cache/profiles/default.json` 时按默认 umask 落 644——内含完整 cookie，auth 后必须 `chmod 600` 补权。

## 要点

- yt-dlp 全局配置在 `~/.config/yt-dlp/config`（代理 + js-runtimes node + bilibili cookie），裸调用即正确。
- `danmaku` 是伪字幕轨（XML），`--sub-langs 'all,-danmaku'` 必须排除否则 ffmpeg 报错。
- BBDown 安装坑：nilaoda/BBDown 已归档停更、默认分支是 DELETED 占位——别走 release/AUR，用 `scripts/install_bbdown.sh`（master 源码 `dotnet publish`，幂等，有源码树自动 fetch+reset）。
- 无字幕轨 → 退出码 3，交给 `--media` + asr 管线，本 skill 不转写。
- 出口码：0 成功；2 URL 不认/参数错；3 无可用文本轨；4 内容已删除；5 车道全挂；6 auth 失效/challenge 需人工；7 超预算。

## 缓存（lgc）

全部连接器走统一缓存层 lgc（`scripts/lgc`，`setup.sh` 软链 `~/.local/bin/lgc`；缺席自动降级为无缓存直通，行为完全一致）。根 `~/.cache/link-get/`。契约全文：`references/cache.md`。

- **键**：`article:<url>` / `wechat:<url>` / `yt:{fast,tr,subs,text}:<vid>` / `bili:{subs,opus,b23}:<id>` / `xyzfm:{tr,art}:<eid>` / `media:<id>#<cred8>`；车道级 `lane:<lane>:<key>` 永不带 cred。
- **TTL**：article/wechat 7d、yt.tr/subs 与 bili.subs/b23 30d、yt.fast/bili.opus 7d、xyzfm.tr 30d、xyzfm.art 7d、media 30d。负缓存：`deleted` 90d→exit 4、`notrack` 24h→exit 3、`unavailable/ratelimited` 15min→exit 5；车道级 `lane-fail` 1h、breaker 600s 内 3 连败跳 600s。
- **旗标**：`--refresh`（跳过全部缓存读、成功仍写回；jina 加 `X-No-Cache`）、`--no-cache`（读写全绕=裸行为）、`--cache-ttl SEC`（本次正缓存 TTL 覆盖）。等价 env：`LGC_REFRESH`/`LGC_OFF`/`LGC_TTL`，子进程继承。
- **命中**：stderr 打 `cache: hit(<lane>,<age>)`，照常 `==> 已存 <path>`。
- **media-get satisfies**：束记 `height`+`req_cap`+`langs_obtained`，命中 iff `height ≤ --max-height ≤ req_cap` 且请求 langs ⊆ 已得 ∪ 证缺；不满足自动重抓。
- **自救**：`lgc stats` / `lgc list link-get` / `lgc explain link-get <键>` / `lgc clear link-get <键>` 或 `--all`；cookie 轮换后 `lgc clear --cred <旧cred8>`、`lgc prune --dead-cred`。
- **回滚**：`LGC_OFF=1 <cmd>` 单次绕；`rm ~/.local/bin/lgc` 全 skill 降级；见 `references/cache.md`「回滚四式」。

## 体检

`scripts/doctor.sh`：入口 / 连接器 / 凭证管线 + `fetch-engine selftest --deploy`（lgc cap 握手 + 全 pack 结构/tools/creds/probe.sh 体检）。单 pack 体检：`fetch-engine selftest -p <pack>`。
