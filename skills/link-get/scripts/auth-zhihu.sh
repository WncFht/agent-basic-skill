#!/bin/bash
# 一次粘贴 cURL，把 cookie 分发到 zhihu-cli 与 zhihu-scraper。
# 用法：
#   auth-zhihu.sh                  # stdin 粘贴 DevTools 的 Copy as cURL
#   auth-zhihu.sh 'curl ...'       # cURL 作为参数
#   auth-zhihu.sh --cookie 'z_c0=xx; d_c0=yy'   # 只给 cookie 头
#   auth-zhihu.sh --from-cli       # 复用 zhihu-cli 已扫码登录的 cookie（先 zhihu auth login）
set -eo pipefail

CONF="$HOME/.config/zhihu-skill"
mkdir -p "$CONF"

if [ "${1:-}" = "--from-cli" ]; then
  # 从 zhihu-cli 已登录的 profile 抽 cookie 分给其余工具（配合 zhihu auth login 扫码用）
  PROF="$HOME/.zhihu-cli/cache/profiles/default.json"
  [ -f "$PROF" ] || {
    echo "没有 $PROF，先跑 zhihu auth login 扫码" >&2
    exit 1
  }
  COOKIE="$(python3 -c "import json;print(json.load(open('$PROF'))['Cookie'])")"
  CURL="" # --from-cli 模式下不回喂 zhihu auth paste
elif [ "${1:-}" = "--cookie" ]; then
  COOKIE="$2"
  UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
  CURL="curl 'https://www.zhihu.com/' -H 'cookie: $COOKIE' -H 'user-agent: $UA'"
else
  if [ $# -gt 0 ]; then CURL="$*"; else CURL="$(cat)"; fi
  # 从 cURL 里提取 cookie 头（-H 'cookie: ...' 或 -b '...'）与 UA
  COOKIE="$(printf '%s' "$CURL" | grep -oE "(-H|--header) 'cookie: [^']*'" | head -1 | sed -E "s/^[^']*'cookie: //; s/'$//")"
  [ -z "$COOKIE" ] && COOKIE="$(printf '%s' "$CURL" | grep -oE " --(cookie|b) '[^']*'" | head -1 | sed -E "s/^[^']*'//; s/'$//")"
  UA="$(printf '%s' "$CURL" | grep -oE "(-H|--header) 'user-agent: [^']*'" | head -1 | sed -E "s/^[^']*'user-agent: //; s/'$//")"
fi

[ -z "$COOKIE" ] && {
  echo "没解析到 cookie，检查粘贴内容" >&2
  exit 1
}
Z_C0="$(printf '%s' "$COOKIE" | tr ';' '\n' | sed -n 's/^ *z_c0=//p' | head -1)"
D_C0="$(printf '%s' "$COOKIE" | tr ';' '\n' | sed -n 's/^ *d_c0=//p' | head -1)"
[ -z "$Z_C0" ] && {
  echo "cookie 里没有 z_c0——这是登录态主键，确认知乎已登录再复制" >&2
  exit 1
}
[ -z "$D_C0" ] && echo "警告: 没有 d_c0，签名接口会失败。建议整段 Copy as cURL 重试" >&2

printf '%s' "$CURL" >"$CONF/curl.txt"
printf '%s' "$COOKIE" >"$CONF/cookie.txt"
printf '{\n  "z_c0": "%s",\n  "d_c0": "%s"\n}\n' "$Z_C0" "$D_C0" >"$CONF/cookies.json"
chmod 600 "$CONF"/curl.txt "$CONF"/cookie.txt "$CONF"/cookies.json

# zhihu-scraper settings.toml（无 cookie 值，只指路径）
cat >"$CONF/settings.toml" <<EOF
[archive]
output_dir = "知乎归档"
markdown = true
media_download = true

[network]
cookie_file = "$CONF/cookies.json"

[browser]
fallback = "auto"
headless = false
# cdp_url = "http://127.0.0.1:9222"   # 本机 Chrome 调试模式启动后可读已登录 cookie
EOF

echo "==> zhihu-cli"
if [ -n "$CURL" ]; then
  printf '%s' "$CURL" | zhihu auth paste
else
  echo "（--from-cli 模式，跳过回喂）"
fi

echo "==> zhihu-scraper"
zhihu-scraper check -s "$CONF/settings.toml" || true

cat <<'EOF'

==> MediaCrawler 不走 cookie 粘贴，二选一：
  a) CDP 骑已登录 Chrome（推荐）：
     /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
     然后 config/base_config.py 设 ENABLE_CDP_MODE = True
  b) 扫码：cd ~/.local/share/zhihu-tools/MediaCrawler && uv run python main.py --platform zhihu --lt qrcode --type detail
EOF

echo "完成。跑 scripts/doctor.sh 复核。"
