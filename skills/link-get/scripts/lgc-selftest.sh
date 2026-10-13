#!/bin/bash
# lgc-selftest.sh — bash 端到端冒烟 + LGC-PROBE-BLOCK conformance。
# 每个 WP 的 gate 复跑本脚本；临时目录一律在 $HOME/.cache 下（/tmp tmpfs 满）。
set -eo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
LGC_BIN="${LGC_BIN:-$SELF/lgc}"
CANON="$SELF/connectors/_lgc.sh"
mkdir -p "$HOME/.cache" # 全新 macOS 无此目录，mktemp 会失败
WORK="$(mktemp -d "$HOME/.cache/lgc-st-sh.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export LGC_HOME="$WORK/home"
mkdir -p "$LGC_HOME"

ok() { echo "  ✓ $*"; }
bad() {
  echo "  ✗ $*"
  FAILED=1
}
FAILED=0
RUN_RC=0
run_rc() {
  RUN_RC=0
  "$@" || RUN_RC=$?
  return 0
} # set -e 下安全抓 rc

echo "== lgc 二进制自测"
run_rc "$LGC_BIN" selftest
{ [ "$RUN_RC" -eq 0 ]; } && ok "lgc selftest" || bad "lgc selftest"
[ "$("$LGC_BIN" --version 2>/dev/null)" = "lgc 1.0" ] &&
  ok "--version" || bad "--version"
"$LGC_BIN" has 2>/dev/null | head -1 | grep -qE '^lgc [0-9]+(\.[0-9]+)?$' &&
  ok "has banner" || bad "has banner"

echo "== rc 抽样"
mkdir -p "$WORK/s"
echo hi >"$WORK/s/a.md"
echo bye >"$WORK/s/b.md"
run_rc "$LGC_BIN" get link-get 'article:st'
[ "$RUN_RC" -eq 1 ] && ok "miss rc1" || bad "miss rc=$RUN_RC"
run_rc "$LGC_BIN" get link-get 'article:st' --claim
[ "$RUN_RC" -eq 6 ] && ok "claim rc6" || bad "claim rc=$RUN_RC"
run_rc "$LGC_BIN" release link-get 'article:st'
run_rc "$LGC_BIN" put link-get 'article:st' --files "$WORK/s/a.md"
[ "$RUN_RC" -eq 0 ] && ok "put rc0" || bad "put rc=$RUN_RC"
run_rc "$LGC_BIN" get link-get 'article:st'
[ "$RUN_RC" -eq 0 ] && ok "hit rc0" || bad "hit rc=$RUN_RC"
run_rc "$LGC_BIN" neg link-get 'article:std' --reason deleted
run_rc "$LGC_BIN" get link-get 'article:std'
[ "$RUN_RC" -eq 4 ] && ok "neg-deleted rc4" || bad "neg-deleted rc=$RUN_RC"

echo "== arxivtex kind / cred-fp / prune --dead-cred"
run_rc "$LGC_BIN" has kind:arxivtex
[ "$RUN_RC" -eq 0 ] && ok "has kind:arxivtex" || bad "has kind:arxivtex"
run_rc "$LGC_BIN" put link-get 'arxivtex:2305.12345' --value texsrc
[ "$RUN_RC" -eq 0 ] && ok "arxivtex put" || bad "arxivtex put rc=$RUN_RC"
run_rc "$LGC_BIN" get link-get 'arxivtex:2305.12345'
[ "$RUN_RC" -eq 0 ] && ok "arxivtex get" || bad "arxivtex get rc=$RUN_RC"
ka="$("$LGC_BIN" key link-get 'arxiv:2305.12345')"
kt="$("$LGC_BIN" key link-get 'arxivtex:2305.12345')"
[ "$ka" != "$kt" ] && ok "arxivtex key distinct" || bad "arxivtex collapses to arxiv"
NH="$WORK/nh"
mkdir -p "$NH/.config/zhihu-skill"
echo cookie >"$NH/.config/zhihu-skill/cookie.txt"
run_rc env HOME="$NH" "$LGC_BIN" cred-fp zhihu
[ "$RUN_RC" -eq 0 ] && ok "cred-fp rc0" || bad "cred-fp rc=$RUN_RC"
run_rc "$LGC_BIN" cred-fp no-such-domain
[ "$RUN_RC" -eq 3 ] && ok "cred-fp unknown rc3" || bad "cred-fp rc=$RUN_RC"
run_rc env HOME="$WORK/nh-empty" "$LGC_BIN" cred-fp zhihu
[ "$RUN_RC" -eq 3 ] && ok "cred-fp no-files rc3" || bad "cred-fp rc=$RUN_RC"
run_rc "$LGC_BIN" prune --ns link-get --dead-cred --dry-run
[ "$RUN_RC" -eq 0 ] && ok "prune --dead-cred --dry-run" || bad "prune rc=$RUN_RC"

echo "== 并发 put 无撕裂"
for _ in 1 2 3 4; do
  "$LGC_BIN" put link-get 'article:cc' --files "$WORK/s/a.md" >/dev/null 2>&1 &
  "$LGC_BIN" put link-get 'article:cc' --files "$WORK/s/b.md" >/dev/null 2>&1 &
done
wait || true
run_rc "$LGC_BIN" get link-get 'article:cc' --into "$WORK/cc"
[ "$RUN_RC" -eq 0 ] && ok "concurrent put → hit" || bad "concurrent get rc=$RUN_RC"
n=$(ls "$WORK/cc" 2>/dev/null | wc -l | tr -d ' ')
[ "$n" = "1" ] && ok "one coherent version" || bad "torn bundle ($n files)"

echo "== 部分清空退化"
find "$LGC_HOME/link-get/blobs" -type f ! -name manifest.json -delete 2>/dev/null || true
run_rc "$LGC_BIN" get link-get 'article:cc'
[ "$RUN_RC" -eq 1 ] && ok "rm -rf blob → miss" || bad "partial clear rc=$RUN_RC"

# extract_probe_block <file> — 打印 marker 块文本（供四份拷贝对账）
extract_probe_block() {
  sed -n '/^# LGC-PROBE-BLOCK v1/,/^# \/LGC-PROBE-BLOCK/p' "$1" 2>/dev/null
}

echo "== PROBE-BLOCK conformance"
CB="$WORK/canon.block"
extract_probe_block "$CANON" >"$CB"
[ -s "$CB" ] && ok "canonical block extracted" || bad "canonical block empty"
check_block() { # $1=file（无 marker 块=未接线，跳过——wp2+ 才会嵌入）
  [ -f "$1" ] || {
    echo "  - $(basename "$1") (absent, skip)"
    return 0
  }
  extract_probe_block "$1" >"$WORK/this.block"
  [ -s "$WORK/this.block" ] || {
    echo "  - $(basename "$1") (no block yet, skip)"
    return 0
  }
  if cmp -s "$CB" "$WORK/this.block"; then
    ok "block match: $(basename "$1")"
  else
    bad "PROBE-BLOCK drift: $1"
    diff -u "$CB" "$WORK/this.block" >&2 || true
  fi
}
check_block "$SELF/connectors/_lgc.sh"
# python 嵌入副本互相对账：实现与 bash canon 不同源（各自语言的探针），
# 但多份 python 拷贝之间必须 byte-identical；zhihu-tardis 现运行时 source
# canon 不内嵌（probe.sh / test_zhihu_tardis.py 亦守此不变量）。
PYB="$WORK/py.block"
extract_probe_block "$SELF/connectors/canvas-get" >"$PYB"
if [ -s "$PYB" ]; then
  extract_probe_block "$SELF/connectors/media-get" >"$WORK/this.block"
  if cmp -s "$PYB" "$WORK/this.block"; then
    ok "python block match: media-get"
  else
    bad "python PROBE-BLOCK drift: media-get"
    diff -u "$PYB" "$WORK/this.block" >&2 || true
  fi
else
  bad "canvas-get python block empty"
fi
grep -q 'LGC-PROBE-BLOCK' "$SELF/connectors/zhihu-tardis" &&
  bad "zhihu-tardis 内嵌 PROBE-BLOCK" || ok "zhihu-tardis no embedded block"

[ "$FAILED" -eq 0 ] && echo "lgc-selftest.sh: ALL GREEN" || echo "lgc-selftest.sh: FAILURES"
exit "$FAILED"
