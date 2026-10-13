# shellcheck shell=bash
# shellcheck disable=SC2034 # ZHIT/ZRC/ZNEG/ZPATHS/ZDEL/ZVAL are the caller-facing API
# _lgc.sh — canonical lgc helper block (bash ≥3.2, BSD-safe).
# 单源（Phase-5a）：本文件即唯一事实源（旧 skills/zhihu 已删）。
# zhihu-tardis 运行时 source 本文件，缺席时装
# no-op stub 全 miss 降级（不再是内嵌副本）。
#
# Rules baked in here (finalPlan D12/D13/D14):
#   * every public helper is safe under set -e: z_probe is ALWAYS rc0 and
#     reports through ZHIT/ZRC/ZNEG/ZPATHS; all write helpers end `|| true`.
#   * no bare `lgc` calls outside these helpers — key/cat/list are wrapped
#     (z_key/z_cat/z_list) so a missing lgc never rc127s a connector.
#   * flag veto (§4.1 C): a flag whose cap is absent vetoes the WHOLE call
#     to miss/no-op — we never silently drop a flag and fire a degraded call.

# LGC-PROBE-BLOCK v1
LGC_BIN="${LGC_BIN:-lgc}" # 改它必须 unset LGC_CAPS
_lgc_probe() {            # 惰性每进程一次；LGC_CAPS export 子进程链继承
  [ -n "${LGC_OFF:-}" ] && {
    LGC_CAPS=""
    export LGC_CAPS
    return 1
  }
  if [ -z "${LGC_CAPS+x}" ]; then
    LGC_CAPS=""
    if command -v "$LGC_BIN" >/dev/null 2>&1; then
      local out
      out="$("$LGC_BIN" has 2>/dev/null)" || out=""
      printf '%s\n' "$out" | head -1 | grep -qE '^lgc [0-9]+(\.[0-9]+)?$' &&
        LGC_CAPS="$(printf '%s\n' "$out" | tail -n +2 | tr '\n' ' ')"
    fi
    export LGC_CAPS # 空串=已探缺席；unset=未探（${LGC_CAPS+x} 区分）
  fi
  [ -n "$LGC_CAPS" ]
}
_lgc_has() { case " $LGC_CAPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac }
# /LGC-PROBE-BLOCK

# --- z_probe <ns> <key> [flags...] — always rc0 -----------------------------
# Sets ZHIT=hit|miss|off, ZRC=<lgc rc>, ZNEG=<reason>, ZPATHS=<materialized>.
z_probe() {
  ZHIT=miss
  ZRC=1
  ZNEG=""
  ZPATHS=""
  local ns="$1" k="$2"
  shift 2 || return 0
  [ -z "$k" ] && return 0
  [ -n "${LGC_OFF:-}" ] && {
    ZHIT=off
    printf 'cache: off\n' >&2
    return 0
  }
  _lgc_probe || {
    ZHIT=off
    printf 'cache: off\n' >&2
    return 0
  }
  local args=() veto="" a
  while [ $# -gt 0 ]; do
    case "$1" in
    --into | --wait | --satisfies | --require-producer | --owner-pid)
      a="${1#--}"
      a="${a%%-*}"
      [ "$1" = "--require-producer" ] && a="producer"
      [ "$1" = "--owner-pid" ] && a="claim"
      _lgc_has "$a" || {
        veto="$1"
        break
      }
      args+=("$1" "$2")
      shift 2
      ;;
    --claim | --json)
      a="${1#--}"
      _lgc_has "$a" || {
        veto="$1"
        break
      }
      args+=("$1")
      shift
      ;;
    *)
      veto="$1" # 不识旗标同样整条 veto，不静默丢弃
      break
      ;;
    esac
  done
  if [ -n "$veto" ]; then
    printf 'cache: miss\n' >&2
    return 0 # 缺 cap → 整条 miss，不丢旗标
  fi
  local out
  ZRC=0
  out="$("$LGC_BIN" get "$ns" "$k" "${args[@]}" 2>&1)" || ZRC=$?
  printf '%s\n' "$out" | grep -E '^(cache|lgc): ' >&2 || true
  case $ZRC in
  0)
    ZHIT=hit
    ZPATHS="$(printf '%s\n' "$out" | grep -vE '^(cache|lgc): ' || true)"
    ;;
  3)
    ZHIT=neg
    ZNEG=notrack
    ;;
  4)
    ZHIT=neg
    ZNEG=deleted
    ;;
  5)
    ZHIT=neg
    ZNEG=unavailable
    ;;
  *) ZHIT=miss ;;
  esac
  return 0
}

# --- z_store <ns> <key> [--lane L] (--files F…|--from DIR|--value V) --------
# Always rc0 (|| true inside). Sets ZDEL=1 when put refused by delguard rc4
# or by the inline-grep fallback (delguard cap absent).
z_store() {
  ZDEL=0
  local ns="$1" k="$2"
  shift 2 || return 0
  [ -z "$k" ] && return 0
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  local args=() files=() veto="" a fromdir=""
  while [ $# -gt 0 ]; do
    case "$1" in
    --lane | --ttl | --cred | --producer | --params | --owner-pid)
      a="${1#--}"
      a="${a%%-*}"
      [ "$1" = "--owner-pid" ] && a="claim"
      _lgc_has "$a" || {
        veto="$1"
        break
      }
      args+=("$1" "$2")
      shift 2
      ;;
    --atomic | --keep)
      a="${1#--}"
      [ "$a" = "keep" ] && a="keep-flag"
      _lgc_has "$a" || {
        veto="$1"
        break
      }
      args+=("$1")
      shift
      ;;
    --files)
      shift
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do
        files+=("$1")
        shift
      done
      ;;
    --from | --value)
      a="${1#--}"
      _lgc_has "$a" || {
        veto="$1"
        break
      }
      [ "$1" = "--from" ] && fromdir="$2"
      args+=("$1" "$2")
      shift 2
      ;;
    *)
      veto="$1"
      break
      ;;
    esac
  done
  [ -n "$veto" ] && return 0
  if ! _lgc_has delguard; then
    # 安全 cap 缺席 → 内联 grep 五删除签名兜底（刻意冗余；--from 目录同样走查）
    local f dscan=()
    [ ${#files[@]} -gt 0 ] && dscan=("${files[@]}")
    if [ -n "$fromdir" ] && [ -d "$fromdir" ]; then
      while IFS= read -r f; do
        dscan+=("$f")
      done < <(find "$fromdir" -type f \( -name '*.md' -o -name '*.txt' -o -name '__value__' \) 2>/dev/null)
    fi
    for f in ${dscan[@]+"${dscan[@]}"}; do
      case "$f" in
      *.md | *.txt | __value__ | */__value__)
        grep -m1 -qE '该内容已被发布者删除|此内容因违规无法查看|该内容已被删除|该回答已被删除|没有知识存在的荒原' "$f" 2>/dev/null &&
          {
            ZDEL=1
            return 0
          }
        ;;
      esac
    done
  fi
  [ ${#files[@]} -gt 0 ] && args+=(--files "${files[@]}")
  local prc=0
  "$LGC_BIN" put "$ns" "$k" "${args[@]}" >/dev/null 2>&1 || prc=$?
  [ "$prc" -eq 4 ] && ZDEL=1
  return 0
}

# --- z_note <ns> <key> <reason> [ttl] — content-level neg, || true ----------
z_note() {
  local ns="$1" k="$2" r="$3" t="${4:-}"
  [ -z "$k" ] && return 0 # 空键 no-op
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  local args=(--reason "$r")
  [ -n "$t" ] && args+=(--ttl "$t")
  "$LGC_BIN" neg "$ns" "$k" "${args[@]}" >/dev/null 2>&1 || true
  return 0
}

# --- z_lane <ns> <lane> [key] — gate: rc0=跑 / rc1=跳 ----------------------
z_lane() {
  local ns="$1" lane="$2" k="${3:-}"
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0 # lgc 缺席 → 车道放行
  local rc=0
  if [ -n "$k" ]; then
    "$LGC_BIN" lane "$ns" probe "$lane" "$k" 2>/dev/null || rc=$?
  else
    "$LGC_BIN" lane "$ns" probe "$lane" 2>/dev/null || rc=$?
  fi
  [ "$rc" -eq 1 ] && return 1 # lane-neg/breaker → 跳
  return 0                    # 其他 rc（含 2）→ 放行
}

# --- z_lfail <ns> <lane> [key [reason [ttl]]] — breaker++ + 可选车道级 neg -
z_lfail() {
  local ns="$1" lane="$2" k="${3:-}" r="${4:-lane-fail}" t="${5:-}"
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  _lgc_has breaker && "$LGC_BIN" lane "$ns" fail "$lane" >/dev/null 2>&1 || true
  if [ -n "$k" ]; then
    local args=(--reason "$r")
    [ -n "$t" ] && args+=(--ttl "$t")
    "$LGC_BIN" lane "$ns" note "$lane" "$k" "${args[@]}" >/dev/null 2>&1 || true
  fi
  return 0
}

# --- z_val <ns> <key> — value 读出到 ZVAL，恒 rc0 ---------------------------
z_val() {
  ZVAL=""
  ZRC=1
  local ns="$1" k="$2"
  [ -z "$k" ] && return 0
  [ -n "${LGC_OFF:-}" ] && return 0
  [ -n "${LGC_REFRESH:-}" ] && return 0
  _lgc_probe || return 0
  ZRC=0
  ZVAL="$("$LGC_BIN" cat "$ns" "$k" 2>/dev/null)" || ZRC=$?
  return 0
}

# --- z_vput <ns> <key> <value> [extra flags…] — value 写入，|| true ---------
z_vput() {
  local ns="$1" k="$2" v="$3"
  shift 3 || return 0
  [ -z "$k" ] && return 0
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  _lgc_has value || return 0
  "$LGC_BIN" put "$ns" "$k" --value "$v" "$@" >/dev/null 2>&1 || true
  return 0
}

# --- z_rel <ns> <key> — 只清自己认领的 inflight -----------------------------
z_rel() {
  local ns="$1" k="$2"
  [ -z "$k" ] && return 0
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  "$LGC_BIN" release "$ns" "$k" --owner-pid $$ >/dev/null 2>&1 || true
  return 0
}

# --- z_key <ns> <key> — 打短 hash（文件名用）；lgc 缺席回退 cksum -----------
z_key() {
  local ns="$1" k="$2"
  if [ -z "${LGC_OFF:-}" ] && _lgc_probe && _lgc_has key; then
    "$LGC_BIN" key "$ns" "$k" 2>/dev/null && return 0
  fi
  printf '%s' "$k" | cksum | awk '{print $1}' # POSIX 双平台兜底
  return 0
}

# --- z_cat <ns> <key> — value 到 stdout；rc 透传（调用方自行 ||）------------
z_cat() {
  local ns="$1" k="$2"
  [ -n "${LGC_OFF:-}" ] && return 1
  _lgc_probe || return 1
  "$LGC_BIN" cat "$ns" "$k" 2>/dev/null
}

# --- z_list <ns> <glob> — 键清单到 stdout；缺席=空输出 rc0 ------------------
z_list() {
  local ns="$1" g="${2:-*}"
  [ -n "${LGC_OFF:-}" ] && return 0
  _lgc_probe || return 0
  "$LGC_BIN" list "$ns" "$g" 2>/dev/null
}

return 0 2>/dev/null || true
