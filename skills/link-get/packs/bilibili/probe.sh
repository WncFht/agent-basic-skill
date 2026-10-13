#!/bin/bash
# pack bilibili live 探针（fetch-engine selftest -p bilibili 调用，PACK_DIR env 注入）。
# 硬项（计 fail）：ssh/scp/curl/python3 工具、refresh-cookies.sh、bilibili-get
# connector、lanes/bili_mint.py。
# advisory（stderr '!' 行不计 fail）：fht-mba ssh 可达性——mint 是按需操作，
# 主机暂睡不该打红部署体检；cookie 文件缺席/老化同理（mint 就是修它的）。
set -u
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }
warn() { echo "! $*" >&2; }
fails=0
b() {
  fails=$((fails + 1))
  bad "$*"
}

for t in ssh scp curl python3; do
  command -v "$t" >/dev/null 2>&1 && ok "$t → $(command -v "$t")" ||
    b "$t 缺席（mint/fetch 链 dep_absent）"
done

LGET="$(cd "$PACK_DIR/../.." && pwd)"
[ -x "$LGET/scripts/refresh-cookies.sh" ] && ok "refresh-cookies.sh" ||
  b "refresh-cookies.sh 缺席/不可执行（$LGET/scripts/）"
[ -x "$LGET/scripts/connectors/bilibili-get" ] && ok "bilibili-get connector" ||
  b "bilibili-get connector 缺席"
[ -f "$PACK_DIR/lanes/bili_mint.py" ] && ok "lanes/bili_mint.py" ||
  b "lanes/bili_mint.py 缺席"

HOST="${COOKIE_HOST:-fht-mba}"
if command -v ssh >/dev/null 2>&1; then
  if ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    "$HOST" true 2>/dev/null; then
    ok "ssh $HOST 可达（mint 凭证源在线）"
  else
    warn "ssh $HOST 不可达——mint 臂将 dep_absent；查 tailscale/主机（瞬时态不计 fail）"
  fi
fi

for f in "$HOME/.config/link-get/cookies/bilibili.txt" "$HOME/BBDown.data"; do
  if [ -f "$f" ]; then
    age=$((($(date +%s) - $(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")) / 86400))
    if [ "$age" -gt 30 ]; then
      warn "$(basename "$f") 已 ${age} 天——或已过期：link-get --mint <bilibili-url> 重铸"
    else
      ok "$(basename "$f") 已存 ${age} 天"
    fi
  else
    warn "缺 $f——link-get --mint <bilibili-url> 铸"
  fi
done

exit $((fails > 0))
