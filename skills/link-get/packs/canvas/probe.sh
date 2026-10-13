#!/bin/bash
# pack canvas live 探针（fetch-engine selftest -p canvas 调用）：
# PAT 来源 + users/self 200 + openssl。
set -u
ok() { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; }
fails=0
b() {
  fails=$((fails + 1))
  bad "$*"
}

TOK="${CANVAS_TOKEN:-}"
SRC='$CANVAS_TOKEN'
if [ -z "$TOK" ] && [ -f "$HOME/.config/canvas-skill/token" ]; then
  TOK="$(cat "$HOME/.config/canvas-skill/token")"
  SRC='$HOME/.config/canvas-skill/token'
fi
if [ -n "$TOK" ]; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
    -H "Authorization: Bearer $TOK" "https://oc.sjtu.edu.cn/api/v1/users/self")
  [ "$code" = "200" ] && ok "API 200（token: $SRC）" ||
    b "API $code（token 失效？Canvas → 设置 → 批准集成 重新生成）"
else
  b "无 token：写 ~/.config/canvas-skill/token 或设 \$CANVAS_TOKEN"
fi

command -v openssl >/dev/null 2>&1 && ok "openssl" || b "openssl 缺失（LTI 实录解密需要）"

exit $((fails > 0))
