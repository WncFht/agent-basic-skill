# 工具链选型

每环取同类最优、免重度安装、可回退。新机器用 `scripts/setup.sh` 一键装齐，`scripts/doctor.sh` 验收。

## 下载层

整体归 `link-get` skill（`~/.agents/skills/link-get`），本 skill 不再自管下载器：

- `link-get --media` → media-get 连接器：meta.json + cover + video.mp4 + 字幕尝试 + 无字幕抽 audio.wav 一条龙。
- Bilibili 车道内 yt-dlp 主道 + BBDown 自动兜底（AI 字幕、登录态 1080P+/HiRes）；Canvas 实录走 canvas-get（PAT 直通）。
- 车道选型理由、凭证层、lgc 缓存契约见 link-get 文档与 `packs/*/references/`。BBDown 安装坑（仓库归档、须 master 源码 dotnet publish）随安装器归 `link-get/scripts/install_bbdown.sh`。

唯一留在本 skill 的手工逃生舱：登录受限内容（年龄限制/会员视频）`yt-dlp --cookies-from-browser chrome` 重试——yt-dlp 由 link-get dep 保底，不另声明。

## 转写层（无 CC 字幕时）

- **asr skill**（`~/.agents/skills/asr`）：自包含 sherpa-onnx CPU 车道，中文/中英混授课 `--lang zh`（FireRedASR2 zh_en），纯英文 `--lang en`（parakeet-tdt）。模型随 skill 自带、转写不联网；1 h 音频约 4 min。

## 排版层

- **xelatex + ctex** 主线：中文排版金标准（标点压缩、中西文自动间距）。字体集按平台选：`fontset=fandol`（装过 fandol）/`mac`/`windows`。
- **tectonic** 兜底：同 XeTeX 引擎、免维护 TeX Live、按需下载包；xelatex 缺包或环境损坏时顶上（首次运行会下载 bundle）。
- 不采用 Typst：编译极快但 CJK 细节距 ctex 仍有差距，且交付物要求 `.tex` 生态。不采用 lualatex：中文支持依赖 LuaTeX-ja 系，兼容性不如 xelatex+ctex 稳。

## 帧抽取层

- **ffmpeg/ffprobe** 全包：`select` 等距采样（VFR 源必须按真实 pts 采样，不能用 `fps` 网格——两者会对不上时间戳）、`crop`、`tile`/`xstack` 拼图。
- **ImageMagick** montage/label 作接触表备选。
- 不装 PySceneDetect：固定模板 slide 的切页 scene-detect 抓不到，均匀采样接触表才是对的方法。

## PDF 校验层

poppler（pdftoppm/pdfinfo 渲染预览与页数）+ ghostscript（压缩、修复）+ latexmk（自动收敛重跑次数）。

## 维护规则

- 下载失败先升级 link-get 车道（`uv tool upgrade yt-dlp`；BBDown 走 `bash ~/.agents/skills/link-get/scripts/install_bbdown.sh`）——yt-dlp 对平台变化最敏感。
- 新发现的环境坑一律加进 `scripts/doctor.sh` 检查项，不写进 SKILL.md 正文。
- BBDown 首次使用跑 `BBDown login` 扫码，凭据缓存在工作目录 `BBDown.data`（link-get 车道自动复用）。
