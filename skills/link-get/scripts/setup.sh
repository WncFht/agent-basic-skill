#!/bin/bash
# 幂等安装 link-get 与全部连接器：软链进 ~/.local/bin + 依赖检查
set -eo pipefail

BIN_DIR="$HOME/.local/bin"
SELF="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$BIN_DIR" "$HOME/.config/canvas-skill"

ln -sf "$SELF/link-get" "$BIN_DIR/link-get"
ln -sf "$SELF/refresh-cookies.sh" "$BIN_DIR/refresh-cookies"
ln -sf "$SELF/lgc" "$BIN_DIR/lgc"
ln -sf "$SELF/fetch-engine" "$BIN_DIR/fetch-engine"
# connectors/ 下全部入口都上架——不止 *-get（zhihu-tardis、arxiv-tex 不收该后缀）；
# _* 前缀是库文件（_common.sh/_lgc.sh）或 __pycache__ 类内部件，跳过
for c in "$SELF"/connectors/*; do
  [ -f "$c" ] || continue
  case "$(basename "$c")" in _*) continue ;; esac
  chmod +x "$c"
  ln -sf "$c" "$BIN_DIR/$(basename "$c")"
done
chmod +x "$SELF/link-get" "$SELF/refresh-cookies.sh" "$SELF/lgc" "$SELF/fetch-engine"
echo "==> link-get + connectors + refresh-cookies + lgc + fetch-engine → $BIN_DIR"

# 上架烟闸（非致命）：连接器应全经 PATH 可达；全缺多半是 ~/.local/bin 没入 PATH
_missed=""
for c in generic-get wechat-get youtube-get bilibili-get media-get zhihu-get zhihu-tardis canvas-get arxiv-tex; do
  command -v "$c" >/dev/null 2>&1 || _missed="$_missed $c"
done
[ -n "$_missed" ] && echo "警告: 连接器不在 PATH:$_missed（检查 $BIN_DIR 是否入 PATH）"
unset _missed

# lgc 缓存层：三 ns 根 700（-p 不修复存量权限，显式 chmod）
for ns in link-get zhihu-skill canvas-skill; do
  mkdir -p "$HOME/.cache/$ns"
  chmod 700 "$HOME/.cache/$ns" 2>/dev/null || true
done
command -v xattr >/dev/null 2>&1 && {
  for ns in link-get zhihu-skill canvas-skill; do
    xattr -w com.apple.metadata:com_apple_backup_excludeItem \
      com.apple.metadata:com_apple_backup_excludeItem \
      "$HOME/.cache/$ns" 2>/dev/null || true
  done
}
banner="$("$BIN_DIR/lgc" has 2>/dev/null | head -1)"
printf '%s\n' "$banner" | grep -qE '^lgc [0-9]+(\.[0-9]+)?$' ||
  echo "警告: lgc 横幅校验失败（$banner）——缓存层将直通 miss，跑 doctor.sh 排查"

command -v yt-dlp >/dev/null || uv tool install yt-dlp
command -v BBDown >/dev/null || echo "提示: BBDown 未装——跑 bash $SELF/install_bbdown.sh 从源码装（B 站 AI 字幕兜底车道）"
command -v lgc >/dev/null 2>&1 ||
  echo "提示: lgc 不在 PATH（版本戳功能直通关闭；把 $BIN_DIR 加进 PATH）"
[ -f "$HOME/.config/yt-dlp/config" ] || echo "提示: 无 ~/.config/yt-dlp/config，YouTube/B 站可能走不通（代理+js-runtime+cookie）"
# 原 canvas skill setup 的提示检查（PAT / 抽帧 / play-center 签名链）
[ -f "$HOME/.config/canvas-skill/token" ] ||
  echo "提示: 无 ~/.config/canvas-skill/token——写入 PAT（chmod 600）或设 \$CANVAS_TOKEN"
command -v ffmpeg >/dev/null || echo "提示: ffmpeg 未装（无法抽 audio.wav/cover.jpg）"
command -v openssl >/dev/null || echo "提示: openssl 未装（play-center 链接解不了）"

# 知乎三件套（zhihu-cli / zhihu-scraper+补丁 / MediaCrawler）归 sibling 脚本管——
# 重网络安装，失败不连坐（rc 透出警告），可单独重跑
if [ -x "$SELF/setup-zhihu.sh" ]; then
  "$SELF/setup-zhihu.sh" ||
    echo "警告: setup-zhihu.sh 未跑完（rc=$?）——知乎工具链可能缺，可重跑该脚本" >&2
else
  echo "提示: setup-zhihu.sh 不可执行——知乎工具链跳过"
fi

echo "完成。跑 scripts/doctor.sh 复核。"
