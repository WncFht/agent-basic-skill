#!/bin/bash
# pack zhihu live 探针（fetch-engine selftest -p zhihu 调用，PACK_DIR env 注入）。
# 离线项：cookie 文件年龄、MediaCrawler clone、_lgc.sh single-source 对账；
# live 项：zhihu.com / tardis 镜像 / 匿名 article API / scraper cookie / jina。
set -u
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }
fails=0
b() {
  fails=$((fails + 1))
  bad "$*"
}

CONF="$HOME/.config/zhihu-skill"
PROXY="${https_proxy:-${HTTPS_PROXY:-http://127.0.0.1:7890}}"

for c in zhihu zhihu-get zhihu-tardis zhihu-scraper; do
  command -v "$c" >/dev/null 2>&1 && ok "$c → $(command -v "$c")" ||
    b "$c 未安装（跑 setup-zhihu.sh）"
done

code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://www.zhihu.com/" || true)
if [ "$code" = "200" ] || [ "$code" = "302" ]; then
  ok "zhihu.com 可达 ($code)"
else
  b "zhihu.com 不可达 ($code)"
fi

tcode=$(curl -s --noproxy '*' -o /dev/null -w "%{http_code}" --max-time 15 \
  "https://www.zhihu.com/tardis/zm/art/103577237" || true)
# 103577237 是已知已镜像探针 ID；非 200 即通道挂（未镜像属正常覆盖，不在此测）
[ "$tcode" = "200" ] && ok "tardis 探针 ($tcode)" || b "tardis 探针失败 ($tcode)"

if command -v zhihu >/dev/null 2>&1; then
  zhihu browse article 103577237 >/dev/null 2>&1 &&
    ok "匿名 article API" || b "匿名 article API 失败（口子被堵则退回 tardis/Jina）"
  out=$(zhihu auth status 2>&1) && printf '%s\n' "$out" | head -6 | sed 's/^/  /' ||
    b "zhihu auth status 失败（跑 auth-zhihu.sh）"
else
  b "zhihu-cli 不在 PATH"
fi

if command -v zhihu-scraper >/dev/null 2>&1 && [ -f "$CONF/settings.toml" ]; then
  zhihu-scraper check -s "$CONF/settings.toml" >/dev/null 2>&1 &&
    ok "scraper cookie" || b "scraper cookie 失效（重跑 auth-zhihu.sh）"
else
  b "zhihu-scraper 或 $CONF/settings.toml 缺席"
fi

[ -d "$HOME/.local/share/zhihu-tools/MediaCrawler" ] &&
  ok "MediaCrawler clone" || b "MediaCrawler 未 clone（--mc 通道不可用）"

for f in "$CONF/cookies.json" "$HOME/.config/link-get/cookies/bilibili.txt"; do
  if [ -f "$f" ]; then
    age=$((($(date +%s) - $(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f")) / 86400))
    ok "$(basename "$f") 已存 ${age} 天"
  else
    b "缺 $f（refresh-cookies/auth-zhihu.sh）"
  fi
done

code=$(curl -s -o /dev/null -w "%{http_code}" --proxy "$PROXY" --max-time 15 \
  "https://r.jina.ai/" || true)
[ "$code" != "000" ] && ok "r.jina.ai 可达 ($code)" || b "r.jina.ai 不可达（代理 $PROXY）"

# _lgc.sh single-source 对账（搬家后 canon 与 connectors 同目录 sibling-source；
# 旧位 skills/zhihu/scripts/_lgc.sh 只允许缺席或软链回指 canon，实体副本/坏链即漂移）
SKILLS="$(cd "$PACK_DIR/../../.." && pwd)"
CANON="$SKILLS/link-get/scripts/connectors/_lgc.sh"
if [ -f "$CANON" ]; then
  OLD="$SKILLS/zhihu/scripts/_lgc.sh"
  if [ -L "$OLD" ] || [ -e "$OLD" ]; then
    [ -L "$OLD" ] && cmp -s "$CANON" "$OLD" 2>/dev/null &&
      ok "_lgc.sh single-source（旧位软链回指）" ||
      b "zhihu _lgc.sh 漂移（旧位残留非 canon）"
  else
    ok "_lgc.sh single-source"
  fi
  grep -q 'LGC-PROBE-BLOCK' "$SKILLS/link-get/scripts/connectors/zhihu-tardis" 2>/dev/null &&
    b "zhihu-tardis 仍内嵌 PROBE-BLOCK" || ok "tardis 无内嵌块"
fi

exit $((fails > 0))
