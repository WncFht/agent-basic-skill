#!/bin/bash
# pack arxiv live 探针（fetch-engine selftest -p arxiv 调用，亦可裸跑）：
# arxiv-tex connector 三段可解析（ARXIV_TEX>PATH>仓内 connectors/）、uvx
# 在场、lgc arxivtex kind 在场；export.arxiv.org 可达性仅 advisory（戳层
# 本就容错——探测失败不判负）。
set -u
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }
fails=0
b() {
  fails=$((fails + 1))
  bad "$*"
}

PACK_DIR="${PACK_DIR:-$(CDPATH='' cd -P "$(dirname "$0")" && pwd)}"
LGC="${LGC_BIN:-lgc}"

# --- connector 可解析（与 lanes/arxiv_tex.py find_connector 同序） ---------
CONN=""
if [ -n "${ARXIV_TEX:-}" ]; then
  CONN="$ARXIV_TEX"
elif command -v arxiv-tex >/dev/null 2>&1; then
  CONN="$(command -v arxiv-tex)"
else
  CONN="$PACK_DIR/../../scripts/connectors/arxiv-tex"
fi
if [ -n "$CONN" ] && [ -x "$CONN" ]; then
  ok "arxiv-tex → $CONN"
else
  b "arxiv-tex 不可解析（ARXIV_TEX/PATH/connectors/ 三段全落空）"
fi

# --- 运行时硬依赖：uvx（wrapper exec uvx arxiv-to-prompt） ------------------
command -v uvx >/dev/null 2>&1 && ok "uvx" ||
  b "uvx 缺席（curl -LsSf https://astral.sh/uv/install.sh | sh）"

# --- lgc arxivtex kind（内容键规范；缺席→无 kind 归一/TTL 表兜底 HOUR） -----
if command -v "$LGC" >/dev/null 2>&1; then
  if "$LGC" has kind:arxivtex >/dev/null 2>&1; then
    ok "lgc kind:arxivtex"
  else
    b "lgc kind:arxivtex 缺席（跑 6b 后的 lgc 才有——内容键会退化）"
  fi
else
  b "lgc 缺席——缓存/戳层直通降级"
fi

# --- advisory：export.arxiv.org API 可达（版本戳探测同链；失败不闸） -------
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
  'https://export.arxiv.org/api/query?id_list=2305.1234' 2>/dev/null || echo 000)"
case "$code" in
2* | 3*) ok "export.arxiv.org API $code" ;;
*) echo "  · export.arxiv.org 探测 ${code:-000}（advisory：戳层将直通）" ;;
esac

exit $((fails > 0))
