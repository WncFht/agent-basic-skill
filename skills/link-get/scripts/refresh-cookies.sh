#!/bin/bash
# refresh-cookies.sh —— 从 fht-mba 的 Chrome 自动提取并刷新知乎/哔哩哔哩登录态（凭证层共享工具）。
#
#   refresh-cookies.sh          # 刷 zhihu + bilibili 全部
#   refresh-cookies.sh zhihu    # 只刷知乎（z_c0/d_c0 → 同目录 auth-zhihu.sh）
#   refresh-cookies.sh bilibili # 只刷 B 站（Netscape → link-get/cookies + BBDown.data）
#
# Mac keychain 口令从 ~/.config/link-get/mac-keychain.pw（chmod 600）读；
# 缺省时尝试裸解（已解锁时可行）。Canvas 不需要——PAT 无过期问题（见 references/canvas-lti.md）。
set -eo pipefail

LGET_CONF="$HOME/.config/link-get"
ZHIHU_CONF="$HOME/.config/zhihu-skill"
_s="$0"
while [ -h "$_s" ]; do
  _d="$(cd -P "$(dirname "$_s")" && pwd)"
  _s="$(readlink "$_s")"
  case "$_s" in /*) ;; *) _s="$_d/$_s" ;; esac
done
SELF="$(cd -P "$(dirname "$_s")" && pwd)"
unset _s _d
# zhihu 认证脚本已并入本 skill 同目录
ZHIHU_AUTH="$SELF/auth-zhihu.sh"
HOST="${COOKIE_HOST:-fht-mba}"
BILI_TXT="$LGET_CONF/cookies/bilibili.txt"
PW="$(cat "$LGET_CONF/mac-keychain.pw" 2>/dev/null || true)"
SCOPE="${1:-all}"

extract() { # <domain-like> <format> <remote-out>
  scp -q "$SELF/chrome-cookie-extract.py" "$HOST:/tmp/_cce.py"
  ssh "$HOST" "${PW:+security unlock-keychain -p '$PW' ~/Library/Keychains/login.keychain-db 2>/dev/null;}
    python3 -I /tmp/_cce.py --domain '$1' --format '$2' -o '$3' && rm -f /tmp/_cce.py"
}

case "$SCOPE" in
zhihu | all)
  echo "== zhihu：fht-mba Chrome 提取 z_c0/d_c0"
  extract '%zhihu%' header /tmp/_zhihu_cookie.txt
  scp -q "$HOST:/tmp/_zhihu_cookie.txt" "$ZHIHU_CONF/.zhihu_cookie.new"
  ssh "$HOST" 'rm -f /tmp/_zhihu_cookie.txt'
  chmod 600 "$ZHIHU_CONF/.zhihu_cookie.new"
  bash "$ZHIHU_AUTH" --cookie "$(cat "$ZHIHU_CONF/.zhihu_cookie.new")"
  rm -f "$ZHIHU_CONF/.zhihu_cookie.new"
  ;;
esac

case "$SCOPE" in
bilibili | all)
  echo "== bilibili：fht-mba Chrome 提取 SESSDATA 等"
  extract '%bilibili%' netscape /tmp/_bili_cookie.txt
  mkdir -p "$(dirname "$BILI_TXT")"
  scp -q "$HOST:/tmp/_bili_cookie.txt" "$BILI_TXT"
  ssh "$HOST" 'rm -f /tmp/_bili_cookie.txt'
  chmod 600 "$BILI_TXT"
  # BBDown.data：Netscape → cookie 头字符串，media-get 从 $HOME 拾取
  python3 - "$BILI_TXT" <<'PY'
import sys, os
lines = open(sys.argv[1]).read().splitlines()
parts = [f"{f[5]}={f[6]}" for l in lines if l.strip() and not l.startswith("#")
         for f in [l.split("\t")] if len(f) >= 7]
out = os.path.expanduser("~/BBDown.data")
open(out, "w").write("; ".join(parts) + "\n")
os.chmod(out, 0o600)
print(f"  BBDown.data: {len(parts)} cookies")
PY
  echo -n "  登录验证: "
  curl -s -b "$BILI_TXT" "https://api.bilibili.com/x/web-interface/nav" |
    python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print('isLogin:', d.get('isLogin'), '| uname:', d.get('uname'))"
  ;;
esac

echo "完成。跑 ~/.agents/skills/link-get/scripts/doctor.sh 复核。"
