#!/usr/bin/env bash
# video-render-pdf 环境体检：报告必需工具与可选工具，以及已知坑的规避方案。
# 用法: scripts/doctor.sh   （在 skill 运行开始时执行一次）
set -u
ok() { printf "  [ok]      %s\n" "$1"; }
warn() { printf "  [missing] %s\n" "$1"; }
echo "== required =="
for t in ffmpeg ffprobe uvx xelatex pdftoppm; do
  command -v "$t" >/dev/null 2>&1 && ok "$t -> $(command -v $t)" || warn "$t"
done
echo "== optional =="
command -v magick >/dev/null 2>&1 && ok "magick (montage)" || warn "magick — 用 ffmpeg tile/xstack 滤镜代替 montage"
ASR="$HOME/.agents/skills/asr"
[ -x "$ASR/.venv/bin/python" ] && ok "asr skill ($ASR)" ||
  warn "asr skill — $ASR 缺失 venv，跑 bash $ASR/scripts/setup.sh"
{ command -v link-get >/dev/null 2>&1 && command -v media-get >/dev/null 2>&1; } &&
  ok "link-get --media — 素材获取（media-get 连接器）" ||
  warn "link-get --media — 跑 ~/.agents/skills/link-get/scripts/setup.sh"
{ command -v link-get >/dev/null 2>&1 && command -v canvas-get >/dev/null 2>&1; } &&
  ok "link-get <canvas-url> — Canvas 实录（canvas-get 连接器）" ||
  warn "link-get <canvas-url> — 跑 ~/.agents/skills/link-get/scripts/setup.sh"
# yt-dlp / BBDown / JS runtime 是 link-get 车道内件——细查跑 ~/.agents/skills/link-get/scripts/doctor.sh
FV="$HOME/.agents/skills/figure-viz"
[ -x "$FV/scripts/render.py" ] && ok "figure-viz skill — 重绘轨（TikZ/matplotlib + 审计）" ||
  warn "figure-viz skill — $FV/scripts/render.py 缺失，重绘轨不可用"
command -v tectonic >/dev/null 2>&1 && ok "tectonic — xelatex 缺包时的备选引擎" || warn "tectonic — 备选 TeX 引擎"
command -v gs >/dev/null 2>&1 && ok "ghostscript — PDF 压缩可用" || warn "ghostscript — PDF 压缩"
echo "== fonts =="
if kpsewhich FandolSong-Regular.otf >/dev/null 2>&1; then
  ok "fandol fonts ($(kpsewhich FandolSong-Regular.otf)) — ctex 可用 fontset=fandol"
else
  warn "fandol — 跑 scripts/setup.sh 安装，或按平台退回 fontset=mac/windows"
fi
echo "== asr models =="
ls "$HOME/.agents/skills/asr/models" 2>/dev/null | sed 's/^/  model: /' ||
  warn "asr models — bash ~/.agents/skills/asr/scripts/setup.sh"
echo "== env pitfalls =="
# 本机 grep 可能是 ugrep：以 - 开头的 pattern 会被当选项（要 grep -c -- "-->"）
grep --version 2>/dev/null | head -1 | grep -qi ugrep &&
  warn "grep 实为 ugrep —— pattern 以 - 开头时需加 --" ||
  ok "grep = $(grep --version 2>/dev/null | head -1 | cut -c1-40)"
echo "== sheet smoke test =="
# ffmpeg 9 的 xstack layout 表达式 N*w0 求值为 1 导致拼图塌缩；跑两张测试帧验证
ST=$(mktemp -d)
ffmpeg -y -loglevel error -f lavfi -i testsrc2=size=128x72:rate=2:duration=4 \
  "$ST/t.mp4" 2>/dev/null &&
  python3 "$(dirname "$0")/frames.py" grab "$ST/t.mp4" --at 0,1,2,3 \
    --sheet --width 64 --out "$ST" >/dev/null 2>&1
SW=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$ST/candidates.jpg" 2>/dev/null)
if [ "${SW:-0}" -gt 64 ] 2>/dev/null; then
  ok "grab --sheet 拼图正常（${SW}px 宽）"
else
  warn "grab --sheet 拼图塌缩（ffmpeg xstack 兼容性问题）——逐张读候选帧"
fi
rm -rf "$ST"
