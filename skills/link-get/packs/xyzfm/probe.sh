#!/bin/bash
# pack xyzfm live 探针（fetch-engine selftest -p xyzfm 调用，PACK_DIR env 注入）。
# 硬项（计 fail）：python3、三条 lane 文件、api/web-api 可达性。
# advisory（stderr '!' 不计 fail）：token.json 缺席/陈旧/权限错（mint 就是修
# 它的）、qrencode 缺席（QR 降级为纯 URL 提示仍可用）。
set -u
PACK_DIR="${PACK_DIR:-$(CDPATH='' cd -P "$(dirname "$0")" && pwd)}"
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }
warn() { echo "! $*" >&2; }
fails=0
b() {
  fails=$((fails + 1))
  bad "$*"
}

command -v python3 >/dev/null 2>&1 && ok "python3 → $(command -v python3)" ||
  b "python3 缺席（全部 lane dep_absent）"
command -v qrencode >/dev/null 2>&1 && ok "qrencode → $(command -v qrencode)" ||
  warn "qrencode 缺席——mint 的 QR 只给链接不渲图（功能仍可用）"

for f in xyzfm_tr.py xyzfm_sn.py xyzfm_mint.py _lib.py; do
  [ -f "$PACK_DIR/lanes/$f" ] && ok "lanes/$f" || b "lanes/$f 缺席"
done

for h in api.xiaoyuzhoufm.com web-api.xiaoyuzhoufm.com www.xiaoyuzhoufm.com \
  transcript.xyzcdn.net; do
  # 000=curl 未建立连接（不能当 HTTP 码）；任何真 HTTP 响应都算可达
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://$h/" 2>/dev/null || true)
  case "$code" in
  000 | "") b "$h 不可达（curl 无响应）" ;;
  *) ok "$h 可达" ;;
  esac
done

TOK="$HOME/.config/xyzfm/token.json"
if [ -f "$TOK" ]; then
  perm=$(stat -c %a "$TOK" 2>/dev/null || stat -f %Lp "$TOK")
  [ "$perm" = "600" ] || warn "token.json 权限 $perm ≠ 600——chmod 600 $TOK"
  ok "token.json 在（perm $perm）"
else
  warn "token.json 缺席——link-get --mint <episode-url> 扫码铸；无凭证时自动降级 shownotes"
fi

exit $((fails > 0))
