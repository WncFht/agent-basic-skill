# 能力矩阵与边界细节

2026-09 实测。匿名直连 curl 一律 403 zse-ck 挑战（HTML 无 initialState 可抠），api/v4 内容接口匿名 → 403 need_login，~50 请求/IP 触发风控。但匿名面不是零，有四条可用通道：**tardis 镜像**（知乎官方 SEO 面，`/tardis/{zm,bd,sogou}/art/<文章id>`、`/ans/<回答id>`，SSR 全文，只覆盖已镜像子集，未镜像 302→error）、**zhihu-cli 匿名 article API**（ZSE 签名 + 空 d_c0，实测 articles 详情 200，知乎可能随时堵）、**热榜**（browse hot）、**Jina**（约 1/3 被上游拦，要重试 + 走代理）。回答/问题枚举/专栏/用户/评论/zvideo/pin/盐选仍需 z_c0。

## 覆盖矩阵

| 内容类型            | tardis      | Jina      | zhihu-cli                  | zhihu-scraper         | MediaCrawler      |
| ------------------- | ----------- | --------- | -------------------------- | --------------------- | ----------------- |
| 单篇文章 `/p/`      | ✅ 镜像子集 | ✅ 快读   | ✅ download article 可匿名 | ✅ fetch              | ✅ detail 模式    |
| 单条回答            | ✅ 镜像子集 | ✅ 有噪音 | ✅ browse answer           | ✅ fetch              | ✅ detail         |
| 问题全部回答        | ❌          | ❌        | ✅ download question       | ✅ fetch question URL | ✅ detail+ 评论   |
| **专栏整栏枚举**    | ❌          | ❌        | ❌                         | ✅ **唯一**           | ❌                |
| 用户全部作品        | ❌          | ❌        | ✅ download user / scrape  | ❌ 显式拒绝           | ✅ creator 模式   |
| 评论                | ❌          | ❌        | ✅ browse comments         | ✅ 10×10              | ✅ 全树递归       |
| 搜索                | ❌          | ❌        | ✅ search                  | ❌                    | ✅ search_v3 批量 |
| 热榜                | ❌          | ❌(403)   | ✅ browse hot              | ❌                    | ❌                |
| 收藏夹              | ❌          | ❌        | ❌                         | ❌                    | ❌                |
| 盐选                | ❌          | ❌        | ✅ browse yanxuan          | ❌                    | ❌                |
| 用户资料/专栏元数据 | ❌          | —         | ✅ people / API            | ✅                    | ✅                |

## 产物形态差异（选型关键）

- **Jina / zhihu-cli / zhihu-scraper** → Markdown。zhihu-cli 有 YAML frontmatter；zhihu-scraper 用 `>` 引用行记元信息、图片默认下载本地 `media/`、离线 HTML/PDF 可选。
- **MediaCrawler** → CSV/JSON/SQLite，正文是 raw HTML 字段。定位是建数据集，不是直接读；要 md 需二次转换。

## tardis 镜像细节（免登录 tier-0）

- 知乎官方 SEO 镜像面：`www.zhihu.com/tardis/{zm,bd,sogou}/art/<文章id>` 与 `/ans/<回答id>`，完全匿名返回全文 SSR HTML（含 RichText），直连不走代理更稳（知乎按 IP 信誉给面，数据中心代理更糟），连发未见风控。
- **只覆盖已被镜像的内容子集**：未镜像的 ID 一律 302→`/tardis/error?status=500`（实测较新文章 miss 率高）；问题页/专栏/pin/zvideo/收藏夹不覆盖。
- `zhihu-tardis` 脚本封装了改写 + trafilatura 转 md；退出码 3 = 未镜像（让调用方降级），2 = URL 类型不认。

## Jina 细节

- `https://r.jina.ai/<url>` 免 key 20 req/min，**本机要走代理**（`--proxy http://127.0.0.1:7890`）；`-H "X-Return-Format: html"` 返回渲染后完整 DOM（563KB 实测），可本地 trafilatura 二次解析。
- **flaky：约 1/3 请求被上游打 403/「安全验证」**，必须重试（zhihu-get 内置 3 次）。
- 覆盖：单篇文章 ✅、单条回答 ✅（带导航噪音）、问题页 ❌ 403、专栏目录 ❌、收藏夹 ❌。
- 文章不存在时返回「知识荒原」页但 HTTP 200——按标题判 404。
- 行内公式有 `$Q$Q` 重复伪影，要完美公式走 zhihu-cli。

## zhihu-scraper 专栏枚举的机制

`GET /api/v4/columns/{token}/items?limit=N&offset=M` 全量分页，**列表项直接含全文 content**（不逐篇 refetch）。若知乎改为只回摘要则整列失败——这是最大隐性依赖。断点是文件级：重跑重新枚举 + 重拉，但媒体已下载会跳过；`归档进度.md` 逐项追加可人工核对。

## MediaCrawler 三种模式

`config/base_config.py` 里 `CRAWLER_TYPE`：

- `search`：`KEYWORDS` 关键词 → `search_v3` 翻页 → 逐条详情 + 评论树
- `creator`：`ZHIHU_CREATOR_ID_LIST`（url_token 列表）→ `members/{token}/answers|articles|zvideos` 全量 → 评论树
- `detail`：`ZHIHU_SPECIFIED_ID_LIST`（URL 列表）→ 详情 + 评论树

签名不走自研算法：execjs 执行知乎官方 `libs/zhihu.js` 的 `get_sign`，版本漂移时换 JS 文件即可——三工具里最抗变更。代价是要 Node runtime。

`--mc` 封装形态（`link-get --mc` / `zhihu-get --mc` 旁路，不经 engine；`--mc` 吃掉尾部全部参数）：

- `… --mc detail <url>` / `--mc search <kw>` / `--mc creator <token>`，恒带 `--get_comment --get_sub_comment`（评论全树）。
- 登录：`~/.config/zhihu-skill/cookie.txt` 在 → `--lt cookie --cookies` 直注；不在 → MediaCrawler 默认登录（`ENABLE_CDP_MODE` 骑本机 Chrome 已登录会话 / `--lt qrcode` 扫码）。
- 产物落 `~/.local/share/zhihu-tools/MediaCrawler/data/zhihu/`（CSV/JSON/SQLite，正文 raw HTML 字段，要 md 二次转换）。

## z_c0 需求矩阵

| 需求                                                                 | 免 z_c0 车道                                       | 需 z_c0 车道                      |
| -------------------------------------------------------------------- | -------------------------------------------------- | --------------------------------- |
| 单篇文章 `/p/`                                                       | tardis / zhcli（article 匿名面）/ jina / firecrawl | —                                 |
| 单条回答                                                             | tardis（镜像子集）/ jina / firecrawl               | zhcli / scraper                   |
| 问题全回答 / 专栏枚举 / 用户作品 / 评论 / zvideo / pin / 盐选 / 搜索 | —                                                  | zhcli / scraper / MediaCrawler    |
| 热榜                                                                 | zhcli `browse hot`（匿名面）                       | —                                 |
| `--mc` 批量/全树                                                     | —                                                  | cookie.txt 直注或 CDP/qrcode 登录 |

按工具看：tardis / jina / firecrawl 永不需 cookie；zhcli 仅 article + hot 匿名（ZSE + 空 d_c0，随时可能堵，不当长期依赖）；scraper 必须 settings.toml cookie_file；MediaCrawler 必须登录态。

## connector 裸跑（debug 通道）

`zhihu-get <关键词>`（非知乎 URL 的自由文本）走 `zhihu search article` 文章搜索——
要 z_c0，产物是搜索结果表非全文。此面不进 link-get 管线（搜索≠抓取，
bare token 经 canon 判 rc3），仅 connector 单跑可达。
