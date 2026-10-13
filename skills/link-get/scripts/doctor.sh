#!/bin/bash
# link-get 体检：PATH 级入口/连接器烟检 + 凭证管线残留——此处只做浅层在场检查；
# 深检（lgc caps 握手 + pack 结构/lane exec/tools/creds/probe.sh）全归
# `fetch-engine selftest --deploy`（Phase-5b 合一），末尾直接移交。
set -eo pipefail
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }

echo "== 入口"
for c in link-get fetch-engine lgc refresh-cookies; do
  command -v "$c" >/dev/null && ok "$c → $(command -v "$c")" || bad "$c 未安装（跑 setup.sh）"
done

echo "== 连接器"
for c in generic-get wechat-get youtube-get bilibili-get media-get zhihu-get zhihu-tardis canvas-get arxiv-tex; do
  command -v "$c" >/dev/null && ok "$c" || bad "$c 缺失（跑 scripts/setup.sh 重链）"
done

echo "== 凭证管线"
[ -f "$HOME/.config/link-get/mac-keychain.pw" ] && ok "mac-keychain.pw" ||
  bad "无 mac-keychain.pw（refresh-cookies 自动解锁钥匙串需要）"

ENG="$(command -v fetch-engine 2>/dev/null || true)"
if [ -z "$ENG" ]; then
  ENG="$(cd "$(dirname "$0")" && pwd)/fetch-engine"
fi
[ -x "$ENG" ] || {
  echo "fetch-engine 未安装（跑 ~/.agents/skills/link-get/scripts/setup.sh）" >&2
  exit 2
}
exec "$ENG" selftest --deploy
