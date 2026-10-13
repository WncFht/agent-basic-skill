# .crossnote —— MPE 预览环境

`assets/.crossnote/` 是 Markdown Preview Enhanced（shd101wyy.markdown-preview-enhanced）的工作区级定制包，部署到仓库根的 `/.crossnote/`。本机配置（依赖已装扩展 + 用户级设置 + 工作区信任），**不入库**——和 `.claude/` 同属 gitignore 层。

## 内容物

- `parser.js`：QuickJS 单表达式沙箱钩子（onWillParseMarkdown/onDidParseMarkdown）。给**每篇**笔记注入 `theme-toggle.js`（预览 chrome），给含 ` ```pseudocode ` 围栏的笔记追加注入 `pseudocode-runtime.js`，并在导出/预览离线侧把 pseudocode 块预渲染成 `<figure>`。vendored KaTeX+pseudocode 由 `scripts/build-parser.cjs` 拼接进 GENERATED 标记段——**改完跑 `node .crossnote/scripts/build-parser.cjs` 重建**，测试 `node .crossnote/tests/*.test.cjs`。
- `pseudocode-runtime.js`：预览 webview 内的客户端运行时（MutationObserver 管编辑期增量渲染）。
- `theme-toggle.js`：预览右下角的外观选择器——点击弹出 8 项槽位菜单（跟随系统/跟随编辑器/暖纸/羊皮纸/雪白/暖黑/One Dark/纯黑，texlate/Zotero 式双色圆点），写 `body[data-xnote-theme]`，palette 解析在 style.less；localStorage 只对 webview 存活期有效（新面板=新 origin=回到 system），旧值 light/dark 自动映射 paper/dark。
- `style.less`：整套自定义预览主题（`previewTheme: none.css` 把舞台让给它）。配色是 texlate 槽位模型：每槽 {bg, fg} 一对，所有 surface/text/border 变量由 `#paper-slot-light/dark(@bg,@fg)` 按固定比例 color-mix 派生（pdfTheme.ts paletteChromeVars, ADR-0020）；`:root` 默认暖纸，`body[data-xnote-theme="<slot>"]` 切槽，`system`/无属性委托 `body:has(.markdown-preview.system-dark)` → 暖黑。规则全在 `@media screen` 内——打印/导出恒回 :root 暖纸。
- `config.js` / `head.html`：katex/mathjax/mermaid 配置与 `<head>` 注入（script 标签会被 sanitization 剥掉，只剩 link/style/meta）。

## 加载机制（0.8.x 源码实证）

crossnote 读两层目录，合并 `{...编辑器设置, ...全局层, ...工作区层}`——工作区按 key 赢全局：

- 全局：`~/.local/state/crossnote`（`markdown-preview-enhanced.configPath` 设置 > Windows `~/.crossnote` > `$XDG_CONFIG_HOME/crossnote` > `~/.local/state/crossnote`）。无条件加载，缺目录自动建、缺文件自动填默认模板。
- 工作区：`<workspaceRoot>/.crossnote`，目录存在才加载。
- `globalCss`（style.less 编译结果）是唯一拼接键：全局在前、工作区追加。parserConfig / includeInHeader / config.js 各键都是整值覆盖。

## 三个硬约束（决定了部署形态）

1. **经 @import 进预览的 .js 必须 realpath 落在 workspace 内**（pseudocode-runtime.js、theme-toggle.js）。预览端把 `/` 解析为 workspace 根后用 `isPathInsideProjectDirectory` 拦截——该检查走 `realpathSync`，**指到 workspace 外的软链会被解析后拒绝**；`file://`/协议 URL 的 import 在预览里直接跳过。唯一能"跨目录同步"的载体是**硬链**（realpath 不穿透 inode）。
2. **缺文件自动填默认 = 遮蔽全局。** workspace `.crossnote/` 一旦存在，缺失的 parser.js/config.js/head.html 会被写成默认模板，默认值整键覆盖全局层——"只放 runtime、其余吃全局"的混合态不存在，要么整套要么没有。
3. **运行时注入有开关门。** `enablePreviewScripts` 设置 + 工作区受信任双条件，缺一 runtime 不进预览（导出仍走 parser.js 的沙箱预渲染，有静态 figure 兜底）。

## 同步架构：事实源 + 链接农场

- **唯一事实源**：`~/.agents/skills/setup-toolchain/assets/.crossnote/`（`~/.agents` 仓跟踪，测试在这跑——`node tests/*.test.cjs`）。改东西去那里改；`CROSSNOTE_SRC` 环境变量可改指。
- **各仓 `.crossnote/` = 实体目录装链接农场**（obsidian vault 也不例外），由 `scripts/crossnote-links.sh`（入库、幂等）重建：
    - `parser.js`/`style.less`/`config.js`/`head.html`/`README.md` + `scripts`/`tests`/`vendor` → 软链到事实源（readFile 跟软链，无边界检查）
    - `pseudocode-runtime.js`/`theme-toggle.js` → 与事实源同 inode 的**硬链**（过 realpath 检查且双向同步）
    - 在任一仓编辑软链文件 = 直接改事实源，各仓即时同步
- **全局层免费覆盖**：`markdown-preview-enhanced.configPath` 必须在**所有**设置层都不设——全局层才走默认落点 `~/.local/state/crossnote`，其中只有 `style.less` 软链到事实源：没有 `.crossnote` 的仓预览也吃整套主题（`globalCss` 拼接），但 `parser.js`/`config.js`/`head.html` 仍是 MPE 自动填的默认模板——无脚本注入（无外观按钮），pseudocode 围栏也无沙箱预渲染兜底，只按源码块渲染。⚠ configPath 检查要覆盖 User、Machine/Remote（vscode-server 为 `~/.vscode-server/data/Machine/settings.json`，桌面为 `~/.config/Code` 或 macOS `~/Library/Application Support/Code`）、workspace 三层——2026-09-23 `~/.agents` ENOENT 即 Machine 层残留复活旧雷；fht-mba 的 Code User settings 同日也清了同款残留。
- **per-repo 分叉**：把某个软链换成实体文件 = 该键永久分叉（脚本报错拒绝覆盖，是特性）；style.less 可用实体文件写增量（`globalCss` 拼接 = 全局 + 仓内，天然加法）。
- **已知软肋**：编辑器原子保存（写临时再 rename）换 inode → runtime.js 硬链变陈旧→重跑 `crossnote-links.sh` 自愈。其余文件是软链无此问题。
- **全局层软链同款软肋**：`~/.local/state/crossnote/style.less` 若被编辑器经该路径原子保存（写临时再 rename 直接顶掉路径），软链会变成实体副本 → 全局层静默分叉、不再跟随事实源。`crossnote-links.sh` 只管仓内农场不管全局层——断了手动 `ln -sfn <事实源>/style.less ~/.local/state/crossnote/style.less` 指回（默认 `~/.agents/skills/setup-toolchain/assets/.crossnote/style.less`）。
- **无农场的仓降级为纯主题**（不再炸 ENOENT）：早前 configPath 指事实源时，全局 parser 给**每个**工作区注入 `/.crossnote/theme-toggle.js`，无农场仓必炸 `EntryNotFound`（2026-09 ai-news-pipeline 实炸过）；改软链全局层后该雷区消失——代价就是上面说的"吃主题但无脚本注入"。settings 里的 `previewColorScheme` 仍一律 `systemColorScheme`：槽位配色走 `prefers-color-scheme` 媒体查询本不依赖它，但 OS 明暗翻转时 MPE 靠它推刷新重打 `editor-*` 标签，`editor` 槽才能跟上。

## 性能基线与上游杠杆（2026-09-23 全面 profile）

bench：`tests/bench-profile.cjs --deps <quickjs+mpe node_modules>`，fixture 覆盖 6KB–9MB html；QuickJS 上下文跨调用常驻（与 crossnote 一致），所以模块级缓存是合法手段。

已落地的优化（都在事实源，重跑链接脚本即全局生效）：

- **parser.js**：vendored KaTeX+pseudocode（~297KB）延迟 eval——包成 JSON 字符串常量，首个 pseudocode 块才 `ensureVendoredGlobals()`，无围栏文档省掉 ~140ms init；`data-info="pseudocode` indexOf 快速通道 + `hasPseudocodeFence` indexOf 门，无围栏文档 onDid 直接返回；**figure 缓存**（Map，512 条/16MB LRU，key=raw info+classes+id+source，只 unescape miss 路径）配 sentinel 渲染：缓存图以 `CAPTION_SENTINEL` 渲染、命中后把 `7777778` 重打成真序号（caption 三处：文本+id+aria），在上方插入围栏不再使下方全部失效。⚠ 哨兵碰撞必须查**原始输入**（rawSource/rawInfo/rawClasses/rawId 含 `7777778` → 绕缓存直接渲真序号）——查输出命中数必炸：带 caption 的图天然含 3 处，数 >2 会误判永远 miss+ 双重渲染（bench 抓到 warm 3.5→269ms 回归）。
- **pseudocode-runtime.js**：`.hidden-preview`（MPE 滚动同步的隐藏副 DOM）全链路跳过——renderAll/renderDependencyErrors 入口、`nodeContainsSource` 元素门、`runRender` 只认 `UNRENDERED_SOURCE_SELECTOR` 的未渲染源才走依赖链。
- **style.less**：编译产物 122,272→102,480B（−16%）——删 admonition 块/tooltips/`#debug-style()`；callout 变体参数化 mixin（`._callout-colors`/`._callout-icon`），同色组合并、note=default 整条删除；选择器收窄（Prism 后代全是 span→`span`、`li:has(> ul, > ol)`、TOC `a, a *, ol` 替 `*`）；KaTeX 栈收敛为 `--ps-font-family` 变量。
- **`scripts/patch-mpe-globalcss-dedupe.cjs`**（新）：补丁打包态 extension.js 两处——`globalCss` 全局 + 工作区 concat 改相等即单份的三元（农场下 style.less 同源必走单份，`globalCss` 字节量减半）；data-config JSON 里 `globalCss:void 0`（webview 只拿它当 useEffect dep 从不读值，~120KB 白序列化）。幂等、写 `.crossnote-bak`、`node --check` 过再落盘；默认打 `~/.vscode-server` 与 `~/.vscode` 两份 bundle。fht-mba 侧要手动同步跑。
- **`crossnote-links.sh`**：全局层体检——`~/.local/state/crossnote/style.less` 非活链报 error 退出（dangling 时 MPE 读失败会**写穿软链**拿 ~235B 默认 stub 覆盖事实源，比静默分叉严重得多）；实体文件/缺失只 warn。同款写穿对四个工作区软链路径同样成立（`izs`/`szs` 等 stub 填充走 `open(O_CREAT)` 跟随软链，会在事实源位置复活 stub 文件）。

bench 头条（HEAD → 现状，`did` = onDidParseMarkdown）：rl-textbook（9.1MB html）qjs 434→271ms、warm 143→25ms；toc-written 37→23ms；csapp 22→11ms；无伪代码文档 warm ≈ 1.4–2.7ms；synthetic-3k（19 块）warm 440→14ms。

**未动的上游杠杆**（都在打包态 extension.js / crossnote 内核，不是 .crossnote 侧能省的）：

- **marshal 边界**是最大的常驻成本：QuickJS↔宿主序列化 ~34µs/KB 入（CJK）/~8µs/KB ASCII、~3µs/KB 出，9MB 文档单次 did 调用 ~230ms 纯搬运——只能在上游减调用次数/体量（如流式、按块 marshal）。
- `updateHtml` 每次 save 对整篇 markdown 重跑完整管线（编辑器端一次、webview 端再 build 一次 DOM = 双重构建）；初次 `parseMD` 建索引 ~9.6s。
- **首次开预览的全工作区索引**（stub-harness 实测，矩阵见下）：notebook `_walkNotebookDir` 递归遍历所有非 gitignore 文件（stat 每个条目、readFile 每个 .md）建 mentions/backlink/search 三张图，**第一帧 html 等索引建完才写**；无磁盘缓存，每个 exthost 会话付一次。**唯一触发：`wikiLinkResolution:"shortest"`**——`enableWikiLinkSyntax:false` 挡不住（语法关了索引照建）；`alwaysShowBacklinksInPreview:true` 实测**不**阻塞首帧，早前"shortest 或 backlinks"的说法作废。**根治（2026-09-23 已落地）**：vault 全量 `[[x]]` 迁为标准相对路径链接 + 各仓设置翻回默认 `relative` + 关 wikilink 语法，首帧 15.6s→2.4s（fs 调用 19,326→23）。缓解备选：walker 认 `.gitignore`（逐目录加载，跳 node_modules/.git），大产物目录可借此排除；`files.exclude` 不生效。
- wikilink 解析 O(n) 逐链接扫全文；`![[embed]]` 转置无缓存，每次全量重读重渲。
- webview 端 markdown 渲染产出的 html 字符串再经一次 innerHTML 全量重建。
- **全局层 live reload 穿不过软链**（inotify 实证）：MPE 唯一的文件触发重载是 `snu()` 对 `~/.local/state/crossnote` 目录的 `fs.watch`，过滤 `a==="change"`——对该目录里软链目标的写入、对目标的原子 rename 覆盖、`ln -sfn` 换链全都零事件命中过滤器。净效果：改事实源 style.less 磁盘即时同步，但已打开的预览不会因文件改动重读配置（要等设置变更/OS 主题翻转/重开等无关触发）。工作区 `.crossnote` 则压根没有 watcher——"各仓即时同步"对两种文件都只是磁盘层成立，预览端一律等下一次无关触发。
- **沙箱钩子失败被静默吞掉**：`onDidParseMarkdown` 等钩子外包 `.catch(()=>identity stub)` 且无日志，单次调用硬上限 5s（`setDeadline(5e3)`）。重文档首渲（~300KB vendored eval + N×~16ms KaTeX）可以整调超时——`prerenderPseudocode` 是 all-or-nothing 的 `html.replace`，abort 丢弃整趟，所有 pseudocode 块回落原始 `<pre>` 且零诊断；预览靠注入的 runtime 自愈，但**导出/打印/PDF 没有 runtime，会静默带着未渲染源码出厂**。更底层：runtime 注入本身由 `onWillParseMarkdown` 完成，整模块 eval 失败会同时带走两个钩子和兜底；也没有熔断——慢性超时文档每次渲染都白付 5s。
- **`String()` 强转钩子返回值**：`__crossnoteCallHook` 对 hook 结果 `String(result)`——任何未来忘了 `return` 的路径 resolve `undefined`，整篇文档被替换成字面 `"undefined"` 且不触发 `.catch`；沙箱两侧都不做类型检查。

2026-09-23 stub-harness 实测矩阵（preview 目标 = vault `科研/paper ToC - written.md`，产出 html ~1.25MB；首帧 = `openPreview` handler 返回到 `webview.html` 首次写入）：

| wikiLinkResolution | enableWikiLinkSyntax | alwaysShowBacklinksInPreview | 首帧 html | fs 调用（vault 侧）                        |
| ------------------ | -------------------- | ---------------------------- | --------- | ------------------------------------------ |
| shortest           | true                 | false                        | 15,581 ms | stat 14,926 + readFile 3,553 + readDir 847 |
| shortest           | false                | false                        | 15,979 ms | 同上量级                                   |
| shortest           | false                | true                         | 14,684 ms | 同上量级                                   |
| relative           | true                 | false                        | 2,354 ms  | readFile 13 + stat 10                      |
| relative           | false                | false                        | 2,535 ms  | 同上                                       |
| relative           | true                 | true                         | 2,583 ms  | 同上                                       |

ai-news-pipeline（110 万文件）同对照：shortest 50,518 ms（stat 105,084 + readFile 15,066 + readDir 5,317 ≈ 12.5 万次）vs relative 2,251 ms（fs 调用 23 次）。热开（同会话二次 openPreview）各配置均 ~0.45–0.56s，说明索引成本只在每会话首次付一次。

迁移校验（同库，2026-09-23）：pre-migration 树 1,292 文件含 10,270 处 `[[..]]`；提交 a1f82660 改写 1,128 文件，b8a0d96f 补 2 处漏网（lopd.md 因并发写竞态漏迁、csapp `#^blockid` 无法映射锚点降级为文件链接）。迁后全量扫描（掩码围栏/行内代码/数学后）：0 残余 wikilink；唯一迁移缺陷即该 block 引用；其余 ~480 处死链均可在 a1f82660^ 复现，属既有问题（`[n](<>)` 占位、扁平化文档 `#id`、手误 slug、`/Users/...` 绝对路径、缺失 pdf/目录），非迁移破坏。

## 部署（setup-toolchain 流程内）

1. 把 `assets/scripts/crossnote-links.sh` 拷进 `<repo>/scripts/`（chmod +x），跑 `bash scripts/crossnote-links.sh` 建链接农场。
2. `.gitignore` 加 `/.crossnote/`（归"本机 agent 层"段，挨着 `/.claude/`）。
3. `.vscode/settings.json` 并入 MPE 键块（assets 里的版本已带）——`enablePreviewScripts` + `mathRenderingOption: KaTeX` + `previewTheme: none.css` 是 .crossnote 的硬依赖。**不写** `wikiLinkResolution:"shortest"`/`enableWikiLinkSyntax:true`（2026-09-23 起全部仓翻回默认并关 wikilink 语法：`shortest` 是首次开预览阻塞式全库索引的唯一触发，实测矩阵见上节；vault 的 `[[x]]` 已全量迁为标准相对链接）。`alwaysShowBacklinksInPreview` 实测不阻塞首帧，可留默认。
4. 可选：暂存 `.md` 的 pseudocode 校验门——`.githooks/pre-commit` 里对 staged `.md` 跑 `node .crossnote/scripts/check-pseudocode.cjs --staged`，**先 `[[ -f ]]` 判存在**：农场缺失（新克隆没跑 crossnote-links.sh）时跳过而非拦截；`git config core.hooksPath .githooks` 激活。脚本 lint 的永远是 cwd 所在仓，与脚本 realpath 无关。
5. 提醒用户：该工作区首次要在 VS Code 里点"信任"，runtime 才会注入。

## 历史备注

事实源 2026-09-14 起在 `~/.agents`（此前在 obsidian vault，vault 仓曾跟踪实体副本——已转为与其他仓一致的链接农场，`git rm --cached` + `/.crossnote/` 入 vault .gitignore）。整套只有一个事实源、N 个农场，没有需要保鲜的第二副本。

`~/.agents` 仓自身 2026-09-23 起也挂了农场（脚本 `scripts/crossnote-links.sh` 入库）——它是真仓、有 AGENTS.md 与 skill 文档要预览，挂农场后脚本注入在仓内同样生效。fht-mba 的 `~/.agents` 是无 remote 的分叉副本（Sep-21 版事实源，无 theme-toggle.js）：同日已清其 Code User settings 的 configPath 并把 `~/.local/state/crossnote/style.less` 改成软链；那边的事实源更新要靠手动同步。
