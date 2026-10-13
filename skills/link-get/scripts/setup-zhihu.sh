#!/bin/bash
# 幂等安装知乎三件套：zhihu-cli（uv tool）、zhihu-scraper、MediaCrawler（clone + uv sync）
set -eo pipefail

TOOLS_DIR="$HOME/.local/share/zhihu-tools"
BIN_DIR="$HOME/.local/bin"
SELF="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$TOOLS_DIR" "$BIN_DIR"

echo "==> zhihu-cli（PyPI 版有 bug，必须 git main）"
uv tool install --force git+https://github.com/KrisTHL181/zhihu-cli

echo "==> zhihu-scraper"
if [ -d "$TOOLS_DIR/zhihu-scraper" ]; then
  # 本地改动一律丢弃——补丁的唯一事实源是 packs/zhihu/patches/*.patch
  git -C "$TOOLS_DIR/zhihu-scraper" checkout -- .
  git -C "$TOOLS_DIR/zhihu-scraper" pull --ff-only
else
  git clone https://github.com/yuchenzhu-research/zhihu-scraper "$TOOLS_DIR/zhihu-scraper"
fi
# 应用本地补丁（如专栏内 answer 项修复）；上游若已修复则提示人工核对
for p in "$SELF/../packs/zhihu/patches"/zhihu-scraper-*.patch; do
  [ -e "$p" ] || continue
  if git -C "$TOOLS_DIR/zhihu-scraper" apply --check "$p" 2>/dev/null; then
    git -C "$TOOLS_DIR/zhihu-scraper" apply "$p"
    echo "    patched: $(basename "$p")"
  elif git -C "$TOOLS_DIR/zhihu-scraper" apply --reverse --check "$p" 2>/dev/null; then
    echo "    patch 已在位: $(basename "$p")"
  else
    echo "    ⚠ patch 打不上: $(basename "$p")（上游可能已修或已漂移，需人工核对）" >&2
  fi
done
(cd "$TOOLS_DIR/zhihu-scraper" && uv sync)
# shim：仓库内命令叫 zhihu，与 zhihu-cli 冲突，包一层改名
cat >"$BIN_DIR/zhihu-scraper" <<'EOF'
#!/bin/sh
exec uv run --project "$HOME/.local/share/zhihu-tools/zhihu-scraper" zhihu "$@"
EOF
chmod +x "$BIN_DIR/zhihu-scraper"

# zhihu-get 统一入口 + zhihu-tardis 免登录镜像通道 → ~/.local/bin
# （setup.sh 的 connectors/* 全量重链已覆盖，此处保留使本脚本可独立跑）
ln -sf "$SELF/connectors/zhihu-get" "$BIN_DIR/zhihu-get"
ln -sf "$SELF/connectors/zhihu-tardis" "$BIN_DIR/zhihu-tardis"
chmod +x "$SELF/connectors/zhihu-get" "$SELF/connectors/zhihu-tardis"

echo "==> MediaCrawler"
if [ -d "$TOOLS_DIR/MediaCrawler" ]; then
  git -C "$TOOLS_DIR/MediaCrawler" pull --ff-only
else
  git clone --depth 1 https://github.com/NanmiCoder/MediaCrawler "$TOOLS_DIR/MediaCrawler"
fi
(cd "$TOOLS_DIR/MediaCrawler" && uv sync && uv run playwright install chromium)

echo
echo "完成。接下来跑 scripts/auth-zhihu.sh 粘贴 cookie 配置认证。"
