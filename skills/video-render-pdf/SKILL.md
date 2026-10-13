---
name: video-render-pdf
description: 从 YouTube、Bilibili 或 SJTU Canvas 课堂实录的讲座、教程或技术分享视频生成专业、详尽、配图丰富的 LaTeX 课程笔记与最终 PDF。当用户提供 YouTube 链接（youtube.com/watch、youtu.be 等）、Bilibili 链接（bilibili.com/video/BV 号、b23.tv 短链）、SJTU Canvas 课程链接（oc.sjtu.edu.cn/courses/<id>）或 v.sjtu.edu.cn play-center 实录分享链接，并希望获得结构化中文教学笔记时使用——笔记需结合视频标题、章节、图表、公式、代码与字幕讲解，首页放置视频原始封面，从可用的最高分辨率源中抽取关键帧作为插图，最终交付物必须包含渲染完成的 PDF。无 CC 字幕可用时回退到本地 ASR 转写（asr skill）。
---

# Video Render PDF

把一个 YouTube、Bilibili 或 SJTU Canvas 课堂实录的讲座视频变成一份完整可编译的中文 `.tex` 笔记和渲染好的 PDF。各平台共用一条流水线，差异只在素材获取。

## 环境

新机器先跑 `scripts/setup.sh` 一键装齐（幂等）；之后每次开工 `scripts/doctor.sh` 体检。ctex 字体集优先 `fontset=fandol`，缺字体时按平台退回 `mac`/`windows`。以下零依赖脚本（`python3`/`bash` 直跑）固化流水线的机械环节，别每次重推命令：

- `link-get --media <URL> -o <dir>`：meta.json → cover → 可下载最高清晰度 video.mp4 → CC 字幕尝试（Bilibili 拿不到时追加 `BBDown --sub-only` 回退，登录态下含 AI 字幕）→ 无字幕自动抽 audio.wav 供 ASR 转写
- `link-get <课程URL> [--lecture N] -o <dir>`：SJTU Canvas 课堂实录入口，PAT 认证免 cookie。不带 --lecture 时先列讲次清单（带 cour_id、已下载与不可点播标记）再选；默认取 PPT 录屏机位（viewNum 5/6，最适合抽帧做笔记），`--camera all` 可拿全部机位；`v.sjtu.edu.cn` play-center 分享链接直接可用（本地解密 teclId 反查教学班）；`--cover-at` 指定封面抽帧时刻（默认 120s，课前常是签到/待机画面，建议取第一页标题 slide 时段）。平台 AI 字幕常未就绪，产物固定含 audio.wav。轻量用途：`--list-courses`/`--files`/`--announcements`/`--assignments` 直走 Canvas REST，不用 LTI、不下视频——「有没有作业/课件」这类问题别再走完整流水线
- `scripts/frames.py timeline|scan|grab|desub`：全片接触表建 slide 时间轴；字幕带安静度扫描找无硬字幕时刻（`--band auto` 自动定带）；定点抽帧并拼候选表；desub 三档去烧录字幕：`median` 快路径 / `auto` 先测带内覆盖率再分派（clean-frames 或逐像素重建，需 `uv run --with numpy`）/ `rebuild` 强制重建
- `scripts/transcript.py srt2ts|slice`：srt 压成 `MM:SS 文本` 时间戳稿；按时段切 seg_N.txt 给分段精读子代理（边界含 ±15s 重叠）
- `scripts/compile.sh <file.tex>`：latexmk/xelatex 编译 + 错误提取 + 页数检查 + 首页预览图

## 平台差异

| 方面     | YouTube                                                  | Bilibili                                                        | SJTU Canvas 课堂实录                                                                                                        |
| -------- | -------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| URL 格式 | `youtube.com/watch?v=`、`youtu.be/`、`youtube.com/live/` | `bilibili.com/video/BVxxxxxxx`、`b23.tv` 短链                   | `oc.sjtu.edu.cn/courses/<id>`（先列讲次再选讲）；`v.sjtu.edu.cn` play-center 分享链接直接可用（自动解密 teclId 反查教学班） |
| 字幕     | 人工字幕优先；按视频语言或用户要求选轨                   | CC 字幕稀缺，`zh-Hans`/`zh-CN`/`zh`/`ai-zh` 优先，常需 ASR 回退 | 平台 AI 字幕常未就绪，默认 ASR 回退                                                                                         |
| 清晰度   | 常规视频无需登录；年龄限制、会员视频要 cookies           | 1080P+ 通常要登录 cookies                                       | 固定多机位流；PAT 直通免 cookie（link-get canvas 车道）                                                                     |
| 多段视频 | 章节（chapters）、播放列表                               | 分 P                                                            | 一讲一条记录；一讲多机位（教师/学生/PPT/合成通道）                                                                          |
| 平台噪声 | 赞助口播、订阅引导                                       | 同上，另有一键三连话术；弹幕不作教学内容来源                    | 课前设备调试、学生自我介绍等长段低信息内容                                                                                  |

登录受限内容（年龄限制、会员视频）唯一手工逃生舱：`yt-dlp --cookies-from-browser chrome` 重试——yt-dlp 由 link-get 车道保底。Bilibili 高清晰度/AI 字幕/弹幕走 link-get 车道内 BBDown 自动兜底。

## 流水线

1. **元数据先行。** 确认标题、章节、时长、封面与字幕可用性。分 P / 播放列表视频先列出全部段落，问用户处理哪几段，再下载。
2. **字幕三级回退。** 平台 CC 字幕（人工轨优先；Bilibili 无轨时 link-get 车道内自动走 BBDown AI 字幕兜底，凭据复用 `BBDown.data`/`BILI_SESSDATA`——不用手调）→ 本地 ASR 转写（asr skill，`~/.agents/skills/asr`）→ 纯视觉模式（音频太差时只靠抽帧）。`link-get --media` 落盘时已完成字幕尝试、无字幕则抽好 `audio.wav`，本步只剩 ASR 调用。保留时间戳，不要过早压成纯文本——插图定位还要用。

    ```
    ASR=~/.agents/skills/asr
    $ASR/.venv/bin/python3 $ASR/scripts/transcribe.py audio.wav \
      --lang zh --out audio.srt                 # 纯英文课 --lang en
    ```

    ASR 是全流水线首个该后台化的长任务，可与 `frames.py timeline` 并行；后台跑时**别接 `| tail`**（缓冲到进程结束，进度与退出码全丢）。`--lang` 没有 auto 检测，先确认音轨语言再选车道：中文与中英混授课都走 `zh`（FireRedASR2 是 zh_en 双语模型），纯英文走 `en`；车道选错输出即乱码，转写后扫一眼文字构成再往下走。zh 有 GPU 车道时换解释器跑：Linux `.venv-qwen/bin/python3`、macOS `.venv-mlx/bin/python3`；en 的 parakeet_cpp 与所有 CPU 兜底都用 `.venv/bin/python3`，`--backend auto` 自挑。sherpa 车道是 VAD 切段 + CTC/transducer 解码（非自回归、段间不串扰，无幻听反馈环）；要喂领域术语热词只有 qwen 后端支持（`--context`）。车道、显存与并发槽位细节见 `~/.agents/skills/asr/SKILL.md`。

3. **封面与视频源。** 封面取元数据里最高分辨率的原图，写 `.tex` 前落地本地并在首页引用；不要拿视频帧冒充封面。抽帧用当前环境真正能下载的最高分辨率，先探测格式列表。Canvas 实录例外：平台无封面图，`link-get` 默认取 120s 处帧——但课前 5–10 分钟常是签到二维码/待机桌面，默认帧若无内容用 `--cover-at` 改取标题页时段（可从 `frames.py timeline` 接触表找第一页内容 slide）。
4. **长视频拆分。** 超过 20 分钟或字幕超过 300 条时不要整体过稿：按章节、分 P 或连贯时间窗切段，有子代理就并行 spawn。标准动作：`transcript.py srt2ts` 出时间戳稿 → `transcript.py slice` 给每段切 `seg_N.txt`（别让子代理自己 awk 截取，容易翻车）→ 按 [references/digest-agent-prompt.md](references/digest-agent-prompt.md) 模板写 prompt（幻灯片上下文槽位是纠错命门）→ 每段回传：教学目标、核心论点、重要公式或代码、需要时间出处的候选插图、待裁决疑点。ASR 会讹转术语（prefill→"preview"、roofline→"除蓝"）并吞掉数字——提示词里带上标题/描述中的术语表，并写死一条：**所有数字必须能用公式自洽复算，对不上的标 `[待核]`**。相邻段留少量重叠，整合时去重。主代理负责统一大纲和连贯叙事——成品是一份课程笔记，不是段落摘要的拼接。

    **多讲/整门课并行。** 一讲一个子代理，交付目录各自独立（`<cour_id>--<slug>/`）互不干扰；课程索引（如 `canvas/index.md`）是共享文件——别让代理并发改它，各代理只在自己目录写 `index-entry.md` 条目草稿，由 leader 统一合并登记并 commit。所有命令用绝对路径或自带 `cd`：后台任务通知会重置 shell cwd。

## 写作

除非用户明确要求其他语言，一律用中文写。**像优秀教师讲课一样写**：每节按 动机 → 主旨 → 机制 → 例子/证据 → 要点 组织，先大白话直觉再形式化。不要按时间顺序倾倒字幕，要重构成有铺垫、有对比的教学顺序。论断必须落在具体的机制、变量、步骤、可观察现象、时间戳或插图上，不写空泛措辞。「不是……而是……」只在视频本身建立了真实对比且有助于澄清机制时用。

- 从 `assets/notes-template.tex` 起手，填元数据块，封面放第一页并与正文插图视觉区分。
- `\section{...}`/`\subsection{...}` 组织全文；每个大节以 `\subsection{本章小结}` 收尾；有一两个值得给的外部链接时加 `\subsection{拓展阅读}`。
- 公式：先用人话说清它想表达什么、为什么在这里出现，再用 `$$...$$` 展示，紧接着平铺列表解释每个符号。
- 代码：用 `lstlisting` 加描述性 `caption`，代码前说明作用、必要时代码后总结预期行为。
- 跳过：寒暄、闲聊、赞助口播、频道运营话术、无信息量的例行对话。保留有实质教学价值的收尾讨论（综合、局限、权衡、开放问题）。
- 全文以 `\section{总结与延伸}` 收尾：讲者的实质收尾 + 你对核心论点、机制与实践含义的结构化提炼 + 概念压缩与跨节联系 + 支撑得起时给开放问题或下一步。
- 任何地方不得出现 `[cite]` 式占位符。

**四类信息框。** 无每节配额，但每个框必须承载具体教学载荷、紧跟激发它的内容；常规叙述留在正文，框不是装饰；图片一律放在框外。

- `importantbox`：核心概念与中心论点——形式化定义、机制总结、类定理陈述、关键算法步骤、密集讲解后的紧凑重述。
- `knowledgebox`：背景与旁支——前置知识、历史脉络、工程背景、设计权衡、术语对比、直觉类比。
- `warningbox`：误解与易错点——记号重载、隐藏假设、误导性启发式、实现陷阱、因果混淆、讲者纠正错误直觉的地方。
- `dialoguebox`：仅对话密集视频——保留一小段信息量大、生动或特别直观的原对话（一问一答或紧密几轮），带说话人标签与具体时间戳，框后说明它为何重要；寒暄和长段转写不用它。

## 插图

**教学需要多少图就配多少图**，不设上限；只去掉重复与低信息帧。好插图：关键公式、示意图、表格、图表、视觉对比、流水线时序、架构视图、逐阶段推进画面。

选帧循环，对每张图执行：

1. **定位**：用带时间戳的字幕找到该概念被讲解的区间；纯视觉模式用均匀时间采样。
2. **密采**：区间内密集抽候选帧，先用 `fps=1/N` + `tile=` 接触表建立全片 slide 时间轴，再回到目标区间细选。宁可过采样再丢，不要从猜测的时间戳直接抽单帧。网格步长会漏掉寿命短于一格的 slide（一页只讲 30s 时整页可能缺席接触表）——对带 `n/N` 页码的 deck，可用页码条拼接核验次序：crop 页码区抽一串时刻再 `magick montage` 拼一条，比读整图便宜一个数量级，还能暴露讲者回翻（页码回退）。
3. **看图**：用图像查看工具逐张检查候选帧与裁剪。OCR 不能代替看图，字幕、文件名、时间戳都不能代替看图。接触表用于召回，保留/丢弃决定必须基于对原图的直接检查。
4. **选终态**：slide、白板、动画逐步构建时，选完全呈现且可读的最完整状态；候选只差一点就继续找。同一窗口里靠后且实质更完整的帧优先。
5. **命名**：视觉确认内容后才改成语义名（描述帧里实际可见的内容）；过渡态与含糊帧继续找，不锁定名字。

**内嵌字幕与遮挡。** 交付帧不得带视频内嵌硬字幕或弹幕。先抽 1 张探测帧确认有无硬字幕、字幕带位置与形态（单行文字 / 气泡 / 双语），再按决策树走：字幕带不压内容 → `grab --crop` 直接裁底；有字幕空隙 → `scan --band auto` 找安静时刻取帧；字幕稀疏但覆盖目标区 → `desub --mode median`；近连续字幕或气泡字幕 → `desub --mode auto`（先测带内覆盖率再分派，输出会打印走了哪条路径）；字幕压真实文字且重建失败 → 局部白化 + caption 补记，或整图重绘。关键事实：白填充 + 黑描边字幕两极亮度同为离群值，覆盖率 >50% 时中位数必然撞极——所以必须先测覆盖率再选算法，盲试 median 只是浪费。窗口必须落在单页 slide 内（拿 scene-detect 点或接触表做硬边界），跨边界的中位数全是糊的。对固定模板 slide 的视频，scene-detect 阈值常常抓不到切页——用均匀采样接触表代替。拼候选表用 `grab --sheet`（ffmpeg xstack），不要手写 `magick montage`（部分环境缺默认字体会报错）。

**时间出处。** 每张视频帧（含裁剪图）在同页用脚注记下来源区间，如 `00:12:31--00:12:46`；区间取定位它的字幕段，不用章节级粗估；多帧同区间时一条脚注即可。用 `[H]` 或非浮动块把图和脚注钉在同页。终帧一律 jpg（`-q:v 2` 直出）——slide 帧走 PNG 只会让 PDF 体积翻倍后再回头转 jpg，白白多一次重编；PNG 只留给确需无损的场合。

**上下文纪律。** 每张候选帧/成图都要进 context 才能做取舍——这是硬成本，要主动预算：批量审帧先看 `grab --sheet` 拼图或字幕带裁剪，全尺寸只读终版；单会话图片 Read 控制在 ~60 次内（实测 ~120 次必触发 compact）。关键中间结论（帧质量判定、crop 坐标表、slide 边界表）随时落 `work/notes.md`，compact 后按文件恢复而不是重读图。

**重绘。** 截图加文字讲不清时走 `figure-viz` skill（`~/.agents/skills/figure-viz`）重画，别手写裸 TikZ/matplotlib——机制/流程/架构/几何直觉/对比表/机制总结图 → TikZ 轨（`.frag` → `scripts/render.py` → 矢量 pdf，vizaudit 机器审计）；scaling/训练/消融曲线、分布与热力图等真实数据图 → matplotlib 轨（spec/imperative → pdf）。产物 `\includegraphics` 进笔记——standalone 渲染让审计闭环独立；确需内联 tikz 时按 figure-viz 文档把 `assets/tikz/vizstyle.tex`/`vizaudit.tex` 拷进笔记工程。不加装饰性图片。

## 交付

- 带时间戳的字幕文件（CC 字幕或 ASR 转写的 `audio.srt`）、首页引用的封面、文档引用的全部图片、`<中文标题>_notes.tex` 与编译好的同名 `.pdf`。
- 交付前检查：无重要教学内容或具体细节丢失；每张帧支撑上下文讲解且为完整呈现态；视觉密度对教学足够。终检对账：`grep -o 'assets/final/[^}]*' *_notes.tex | sort -u` 与 `ls assets/final` 应一致。
- 交付前清理中间产物：`work/`、候选帧、`video.mp4`、`audio.wav`、`meta.json`、LaTeX 编译副产物一律删除（白名单已兜住 git，但磁盘要自己清）。**删 `work/` 之前先回流**：本次为去字幕/抽帧迭代出的可复用脚本、参数组合、slide 边界表，要么改进 `scripts/` 要么写进笔记附录——随手删掉等于下次从零再迭代一遍。
- 仓库内归档遵循 CLAUDE.md/AGENTS.md 的视频笔记交付约定（目录、白名单 .gitignore、index.md 登记、帧图无硬字幕）。

## 资源

- `assets/notes-template.tex`：复制后填写的默认 LaTeX 模板
- `scripts/`：doctor.sh、frames.py、transcript.py、compile.sh（素材获取走 link-get：`--media` / `<canvas-url>` 形态，见「环境」节）
- `references/toolchain.md`：工具链选型理由与维护规则
- `references/digest-agent-prompt.md`：长视频分段精读 subagent 的 prompt 模板
- 兄弟 skill：素材获取走 `~/.agents/skills/link-get`（`--media` / `<canvas-url>` 形态）；重绘走 `~/.agents/skills/figure-viz`；转写走 `~/.agents/skills/asr`
