#!/bin/bash
# _common.sh —— link-get 连接器共享函数库（被 connectors/*-get source，不单独执行）。
# 约定：调用方是 bash 脚本，全局变量 OUT/FAST/TARGET 由 lg_args 填，PROXY 在此统一取。

PROXY="${https_proxy:-${HTTPS_PROXY:-http://127.0.0.1:7890}}"

# --- lgc 缓存层挂钩（D12）：同目录 _lgc.sh 缺席 → 全 miss stub 优雅降级 ------
# 车道函数用 ${ZNS:-link-get}/${ZK:-} 两个全局记账（连接器在车道链前预设 ZK=内容键）。
_cs="${BASH_SOURCE[0]}"
while [ -h "$_cs" ]; do
  _cd="$(cd -P "$(dirname "$_cs")" && pwd)"
  _cs="$(readlink "$_cs")"
  case "$_cs" in /*) ;; *) _cs="$_cd/$_cs" ;; esac
done
_cdir="$(cd -P "$(dirname "$_cs")" && pwd)"
unset _cs _cd
[ -f "$_cdir/_lgc.sh" ] && . "$_cdir/_lgc.sh" || true
unset _cdir
if ! type z_probe >/dev/null 2>&1; then
  # _lgc.sh 缺席/半态 → no-op stub：probe 恒 miss、写路径全 no-op（D12）
  # shellcheck disable=SC2034 # ZHIT/ZRC/ZNEG/ZPATHS 是回传调用方的出参
  z_probe() {
    ZHIT=miss
    ZRC=1
    ZNEG=""
    ZPATHS=""
    return 0
  }
  # shellcheck disable=SC2034 # ZDEL 是回传调用方的出参
  z_store() {
    ZDEL=0
    return 0
  }
  z_note() { return 0; }
  z_lane() { return 0; }
  z_lfail() { return 0; }
  # shellcheck disable=SC2034 # ZVAL/ZRC 是回传调用方的出参
  z_val() {
    ZVAL=""
    ZRC=1
    return 0
  }
  z_vput() { return 0; }
  z_rel() { return 0; }
  z_key() {
    printf '%s' "$2" | cksum | awk '{print $1}'
    return 0
  }
  z_cat() { return 1; }
  z_list() { return 0; }
fi

z_lhit() { # 车道成功 → 复位 breaker（z_store --lane 只记车道名不复位）
  local ns="$1" lane="$2"
  [ -n "${LGC_OFF:-}" ] && return 0
  type _lgc_probe >/dev/null 2>&1 || return 0
  _lgc_probe || return 0
  "${LGC_BIN:-lgc}" lane "$ns" hit "$lane" >/dev/null 2>&1 || true
  return 0
}

lg_args() { # 解析 [-o DIR] [--fast] [-h] → 全局 OUT/FAST/TARGET；usage 由各连接器自供
  while [ $# -gt 0 ]; do
    case "$1" in
    -o | --output)
      OUT="${2:?-o 需要目录参数}"
      shift 2
      ;;
    --fast)
      # shellcheck disable=SC2034 # FAST 由 source 本库的连接器消费
      FAST=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --refresh)
      export LGC_REFRESH=1
      shift
      ;;
    --no-cache)
      export LGC_OFF=1
      shift
      ;;
    --cache-ttl)
      export LGC_TTL="${2:?--cache-ttl 需要秒数参数}"
      shift 2
      ;;
    -*)
      echo "不认得的参数：$1" >&2
      exit 2
      ;;
    *)
      [ -z "$TARGET" ] && TARGET="$1"
      shift
      ;;
    esac
  done
  [ -z "${TARGET:-}" ] && {
    usage
    exit 2
  }
  [ -z "$OUT" ] && OUT="./link-out"
  mkdir -p "$OUT" || {
    echo "输出目录不可用（被同名文件占用或权限不足）：$OUT" >&2
    exit 5
  }
}

sanitize() { # 标题 → 文件名片段：tr 只碰 ASCII（放进多字节会按字节打坏 CJK）；全宽冒号用 sed
  local s
  s="$(printf '%s' "$1" | sed 's/：/-/g' | tr '/\\:' '---' | tr -s ' ' '_' | tr -d '<>"|?*')"
  printf '%s' "${s:0:60}"
}

defuddle() { # 通用文章/微信/YouTube 快读首选
  local url="$1" f="$2"
  command -v npx >/dev/null 2>&1 || return 1 # dep-absent 不记 lane-fail（D28）
  npx -y defuddle parse "$url" --markdown --frontmatter -o "$f" 2>/dev/null
  if [ -s "$f" ] && grep -q '[[:alnum:]]' "$f"; then
    return 0
  fi
  z_lfail "${ZNS:-link-get}" defuddle "${ZK:-}"
  return 1
}

trafi() { # trafilatura 车道：只过普通文章
  local url="$1" f="$2"
  command -v uv >/dev/null 2>&1 || return 1 # dep-absent 不记 lane-fail（D28）
  uv run --quiet --with trafilatura python3 - "$url" "$f" <<'PY'
import sys, trafilatura
html = trafilatura.fetch_url(sys.argv[1])
md = trafilatura.extract(html or "", output_format="markdown", include_links=True) or ""
if not md.strip():
    sys.exit(1)
open(sys.argv[2], "w").write(md)
PY
  if [ -s "$f" ]; then
    return 0
  fi
  z_lfail "${ZNS:-link-get}" trafi "${ZK:-}"
  return 1
}

tvly() { # tavily-hikari 车道：位置参数形态（wp0 修复）；微信系用
  local url="$1" f="$2"
  command -v tvly-hikari >/dev/null 2>&1 || return 1 # dep-absent 不记 lane-fail（D28）
  tvly-hikari extract "$url" --extract-depth advanced --format markdown >"$f" 2>/dev/null
  if [ -s "$f" ]; then
    return 0
  fi
  z_lfail "${ZNS:-link-get}" tvly "${ZK:-}"
  return 1
}

jina() { # 免 key 兜底：flaky（~1/3 被拦），重试 3 次 + 标题判 404
  local url="$1" f="$2"
  local hargs=()
  [ -n "${LGC_REFRESH:-}" ] && hargs=(-H "X-No-Cache: true") # --refresh 绕 jina 边缓存
  for _ in 1 2 3; do
    curl -sL --proxy "$PROXY" --max-time 60 "${hargs[@]}" "https://r.jina.ai/$url" -o "$f"
    if grep -qE "知识荒原|没有知识存在的荒原" "$f" 2>/dev/null; then
      echo "内容不存在或已删除（荒原页）" >&2
      rm -f "$f"
      case "$url" in
      *zhihu.com*)
        # zhihu 目标：荒原=知乎墓碑，可靠删除证据（键经 ZK 传入，空→no-op）
        z_note "${ZNS:-link-get}" "${ZK:-}" deleted
        return 4
        ;;
      *)
        # 非 zhihu：荒原只是提取器失败，车道级 lane-fail 24h，链条继续
        z_lfail "${ZNS:-link-get}" jina "${ZK:-}" lane-fail 86400
        return 1
        ;;
      esac
    fi
    [ -s "$f" ] && grep -q "Title:" "$f" && return 0
    sleep 3
  done
  echo "Jina 3 次重试均失败" >&2
  z_lfail "${ZNS:-link-get}" jina "${ZK:-}"
  return 5
}

firecrawl() { # 云端渲染殿后：反爬最强但烧 credit
  local url="$1" f="$2"
  [ -z "${FIRECRAWL_API_KEY:-}" ] && {
    echo "无 FIRECRAWL_API_KEY，跳过 Firecrawl 兜底" >&2
    z_lfail "${ZNS:-link-get}" firecrawl "${ZK:-}" # D2：dep-absent 也计 breaker
    return 5
  }
  curl -s --proxy "$PROXY" --max-time 90 -X POST "https://api.firecrawl.dev/v1/scrape" \
    -H "Authorization: Bearer $FIRECRAWL_API_KEY" -H "Content-Type: application/json" \
    -d "{\"url\":\"$url\",\"formats\":[\"markdown\"],\"onlyMainContent\":true}" |
    python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('markdown',''))" >"$f"
  if [ -s "$f" ] && grep -q '[[:alnum:]]' "$f"; then
    return 0
  fi
  z_lfail "${ZNS:-link-get}" firecrawl "${ZK:-}" # D2：统一非零→z_lfail，永不发 maxAge
  return 1
}

_yt_meta_cacheable() { # $1=kind $2=prefix → rc0=可缓存；伪 prefix（如 ${BVID:-bili} 兜底值）拒（D3）
  case "$1" in
  yt:meta) printf '%s' "$2" | grep -qE '^[A-Za-z0-9_-]{6,}$' ;;
  bili:meta) printf '%s' "$2" | grep -qE '^BV' ;;
  *) return 1 ;;
  esac
}

yt_meta() { # yt-dlp -J → 存 <prefix>.meta.json，stdout 打 title；$3=kind 入键走文件束（D3）
  local url="$1" prefix="$2" kind="${3:-}"
  local j="$OUT/$prefix.meta.json"
  if [ -n "$kind" ] && _yt_meta_cacheable "$kind" "$prefix"; then
    z_probe "${ZNS:-link-get}" "$kind:$prefix" --into "$OUT" --wait "${LGC_WAIT:-60}"
    if [ "$ZHIT" = hit ] &&
      python3 -c "import sys,json; d=json.load(open(sys.argv[1])); assert isinstance(d,dict); print(d.get('title',''))" "$j"; then
      return 0
    fi
  fi
  for _ in 1 2; do
    yt-dlp -J "$url" >"$j" 2>/dev/null || true
    if python3 -c "import sys,json; d=json.load(open(sys.argv[1])); assert isinstance(d,dict); print(d.get('title',''))" "$j"; then
      [ -n "$kind" ] && _yt_meta_cacheable "$kind" "$prefix" &&
        z_store "${ZNS:-link-get}" "$kind:$prefix" --lane yt-dlp --files "$j"
      return 0
    fi
    sleep 2
  done
  echo "yt-dlp -J 元数据两次均失败：$url" >&2
  return 1
}

yt_transcript() { # YouTube 转录：youtube-transcript-api → 时间戳 md
  local vid="$1" f="$2"
  uv run --quiet --with youtube-transcript-api python3 - "$vid" "$f" <<'PY'
import sys
from youtube_transcript_api import YouTubeTranscriptApi

vid, out = sys.argv[1], sys.argv[2]
ytt = YouTubeTranscriptApi()
try:
    tl = ytt.list(vid)
    t = None
    for lang in ("zh-Hans", "zh", "zh-CN", "zh-TW", "en"):
        try:
            t = tl.find_transcript([lang])
            break
        except Exception:
            continue
    snips = t.fetch() if t else next(iter(tl)).fetch()
except Exception as e:
    print(e, file=sys.stderr)
    sys.exit(1)
lines = []
for s in snips:
    m, sec = divmod(int(s.start), 60)
    h, m = divmod(m, 60)
    ts = f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    lines.append(f"**[{ts}]** {s.text}")
open(out, "w").write("\n".join(lines) + "\n")
PY
  [ -s "$f" ]
}

yt_subs() { # 字幕兜底：yt-dlp 人工轨优先，其次自动轨；$3=id 锚定产物（D4 防跨视频误判）；$4=产物目录
  local url="$1" langs="$2" id="${3:-}" dir="${4:-$OUT}"
  yt-dlp --write-subs --sub-langs "$langs" --convert-subs srt --skip-download \
    -o "$dir/%(title).60s--%(id)s.%(ext)s" "$url" >/dev/null 2>&1 || true
  [ -n "$id" ] || return 1 # 无锚 id → 不信目录里遗留 .srt（跨视频误判）
  ls "$dir"/*--"$id".*.srt >/dev/null 2>&1 && return 0
  ls "$dir"/*--"$id"_p*.*.srt >/dev/null 2>&1 && return 0 # B 站分P %(id)s 可带 _pN
  return 1
}

# --- SSRF 闸（Phase0 §1.1）：_guard_url <url> → rc0 放行 / rc2 拒（stderr 报因）
# 只审字面：非 http(s) scheme、authority 内 %/反斜杠/非 ASCII 字节（IDNA/UTS46
# 障眼与 percent-encoded host 不做解码直接拒）、私网/回环 IP 字面（inet_aton
# 全形态归一）、localhost/*.localhost/*.local/*.internal/*.lan/*.home/*.arpa、userinfo 障眼
# （host 取最末 @ 之后）。不触 DNS——rebinding 与 redirect 后复查归 engine 层。

_guard_deny() { printf 'ssrf-guard: 拒绝 %s（%s）\n' "$1" "$2" >&2; }

_guard_url() {
  local url="$1" rest auth hostport host nip="" nrc=0
  # LC_ALL=C → 下方所有 case 按字节匹配：[^[:print:]] 命中一切非 ASCII/控制字节
  local LC_ALL=C
  case "$url" in
  *[[:space:]]*)
    _guard_deny "$url" "URL 含空白字符"
    return 2
    ;;
  http://* | https://*) ;;
  *)
    _guard_deny "$url" "非 http(s) scheme"
    return 2
    ;;
  esac
  rest="${url#*://}"
  auth="${rest%%[/?#]*}" # authority 止于一 / ? #
  case "$auth" in
  "" | *\\*)
    _guard_deny "$url" "authority 为空或含反斜杠"
    return 2
    ;;
  *%*)
    # %31%32%37%2e%30%2e%30%2e%31 式 percent-encoded host：curl 自解成 127.0.0.1
    _guard_deny "$url" "authority 含 % 编码：$auth"
    return 2
    ;;
  *[^[:print:]]*)
    # 全角点。．｡/全角数字/圈码①②⑦/全角字母——resolver 归一成内网字面
    _guard_deny "$url" "authority 含非 ASCII/控制字节：$auth"
    return 2
    ;;
  esac
  hostport="${auth##*@}" # userinfo 障眼：剥离到最末 @ 之后才是真 host
  case "$hostport" in
  \[*\]*)
    host="${hostport#\[}"
    host="${host%%\]*}"
    ;;
  *:*:*)
    host="$hostport" # ≥2 冒号 → 裸 IPv6 字面（缺 bracket 的非标形也照查）
    ;;
  *)
    host="${hostport%%:*}" # host 或 host:port
    ;;
  esac
  # shellcheck disable=SC2018,SC2019 # 主机名只要 ASCII 小写归一，locale 字母不涉
  host="$(printf '%s' "$host" | tr 'A-Z' 'a-z')"
  while [ "${host%.}" != "$host" ]; do host="${host%.}"; done # FQDN 尾点归一
  if [ -z "$host" ]; then
    _guard_deny "$url" "host 为空"
    return 2
  fi
  case "$host" in
  *\** | *\?* | *\[*) # glob 字符会污染下方分段展开，且合法 host 本就不含
    _guard_deny "$url" "host 含 glob 字符：$host"
    return 2
    ;;
  localhost | *.localhost | *.local | *.internal | *.lan | *.home | *.arpa)
    _guard_deny "$url" "本地/内网主机名：$host"
    return 2
    ;;
  *:*)
    _guard_v6 "$host" "$url"
    return $?
    ;;
  esac
  nip="$(_ip4_norm "$host")" || nrc=$?
  case "$nrc" in
  0)
    _guard_v4 "$nip" "$url"
    return $?
    ;;
  2)
    _guard_deny "$url" "畸形 IP 数字字面：$host"
    return 2
    ;;
  esac
  return 0
}

# _ip4_norm <host_lc> → stdout "a.b.c.d" rc0；rc1=非 IPv4 字面；rc2=畸形数字字面。
# inet_aton 全形态归一：dword / a.b / a.b.c / 点分；段内 0x 十六 / 0 八进制 / 十进制。
_ip4_norm() {
  local h="$1"
  case "$h" in
  "" | *[!0-9a-fx.]*) return 1 ;; # 含非字面字符 → 主机名
  esac
  local IFS=.
  # shellcheck disable=SC2086 # 刻意按 . 分段
  set -- $h
  local n=$# i=0 comp v max vals=""
  IFS=' '
  if [ "$n" -lt 1 ] || [ "$n" -gt 4 ]; then return 1; fi
  for comp in "$@"; do
    i=$((i + 1))
    case "$comp" in
    "") return 2 ;; # 空段（连点）→ 畸形
    0x*)
      comp="${comp#0x}"
      case "$comp" in "" | *[!0-9a-f]*) return 2 ;; esac
      [ "${#comp}" -gt 16 ] && return 2 # ≥17 位 hex 可溢出 int64 回绕正值 → 畸形
      v=$((16#$comp))
      ;;
    0?*)
      case "$comp" in *[!0-7]*) return 2 ;; esac
      [ "${#comp}" -gt 22 ] && return 2 # >22 位（含前导 0）可溢出 int64 → 畸形
      v=$((8#$comp))
      ;;
    *)
      case "$comp" in *[!0-9]*) return 1 ;; esac # a-f 字母段 → 主机名
      [ "${#comp}" -gt 19 ] && return 2          # >19 位十进制可溢出 int64 回绕 → 畸形
      v=$((10#$comp))
      ;;
    esac
    [ "$v" -lt 0 ] && return 2 # 落 (2^63,2^64) 回绕成负值 → 畸形
    if [ "$i" -eq "$n" ]; then # 末段按 inet_aton 语义吞掉剩余字节
      case "$n" in
      1) max=4294967295 ;;
      2) max=16777215 ;;
      3) max=65535 ;;
      *) max=255 ;;
      esac
    else
      max=255
    fi
    [ "$v" -gt "$max" ] && return 2
    vals="$vals $v"
  done
  # shellcheck disable=SC2086 # 刻意空格分段
  set -- $vals
  case "$n" in
  1) printf '%d.%d.%d.%d\n' $(($1 >> 24)) $(($1 >> 16 & 255)) $(($1 >> 8 & 255)) $(($1 & 255)) ;;
  2) printf '%d.%d.%d.%d\n' "$1" $(($2 >> 16)) $(($2 >> 8 & 255)) $(($2 & 255)) ;;
  3) printf '%d.%d.%d.%d\n' "$1" "$2" $(($3 >> 8)) $(($3 & 255)) ;;
  4) printf '%d.%d.%d.%d\n' "$1" "$2" "$3" "$4" ;;
  esac
  return 0
}

_guard_v4() { # 归一化点分 v4 → 私网/回环/组播/保留 rc2（0/8 含 0.0.0.0 一并拒）
  local ip="$1" url="$2" IFS=.
  # shellcheck disable=SC2086 # 刻意按 . 分段
  set -- $ip
  if [ "$#" -ne 4 ]; then
    _guard_deny "$url" "IPv4 归一化失败：$ip"
    return 2
  fi
  if [ "$1" -eq 0 ] || [ "$1" -eq 10 ] || [ "$1" -eq 127 ] ||
    { [ "$1" -eq 100 ] && [ "$2" -ge 64 ] && [ "$2" -le 127 ]; } || # CGNAT 100.64/10（tailnet 段）
    { [ "$1" -eq 169 ] && [ "$2" -eq 254 ]; } ||
    { [ "$1" -eq 172 ] && [ "$2" -ge 16 ] && [ "$2" -le 31 ]; } ||
    { [ "$1" -eq 192 ] && [ "$2" -eq 0 ] && [ "$3" -eq 0 ]; } ||   # 192.0.0/24
    { [ "$1" -eq 192 ] && [ "$2" -eq 88 ] && [ "$3" -eq 99 ]; } || # 192.88.99/24 6to4 relay anycast
    { [ "$1" -eq 192 ] && [ "$2" -eq 168 ]; } ||
    { [ "$1" -eq 198 ] && [ "$2" -ge 18 ] && [ "$2" -le 19 ]; } || # 198.18/15 基准网
    [ "$1" -ge 224 ]; then                                         # 224/4 组播 + 240/4 保留（含 255.255.255.255）
    _guard_deny "$url" "IPv4 私网/回环/组播/保留：$ip"
    return 2
  fi
  return 0
}

_v4of() { # 两个十进制 hextet → 点分 v4 串（v6 嵌入段复核用）
  printf '%d.%d.%d.%d\n' "$(($1 >> 8))" "$(($1 & 255))" "$(($2 >> 8))" "$(($2 & 255))"
}

# _ip6_hextets <host_lc> → stdout 8 个十进制 hextet；rc1=畸形。
# 处理 :: 压缩与尾嵌点分 v4（::ffff:a.b.c.d 等形）。
_ip6_hextets() {
  local h="$1" v6="$1"
  case "$h" in
  *.*)
    case "$h" in *:*) ;; *) return 1 ;; esac
    local v4d="${h##*:}" ip a b c d r r2
    ip="$(_ip4_norm "$v4d")" || return 1
    a="${ip%%.*}"
    r="${ip#*.}"
    b="${r%%.*}"
    r2="${r#*.}"
    c="${r2%%.*}"
    d="${r2#*.}"
    v6="${h%:*}:$(printf '%x:%x' $((a * 256 + b)) $((c * 256 + d)))"
    ;;
  esac
  local left="" right="" comp=0
  case "$v6" in
  *::*)
    left="${v6%%::*}"
    right="${v6#*::}"
    comp=1
    ;;
  *) left="$v6" ;;
  esac
  local IFS=: nl=0 nr=0 lp="" rp="" t res="" i
  if [ -n "$left" ]; then
    # shellcheck disable=SC2086 # 刻意按 : 分段
    set -- $left
    nl=$#
    lp="$left"
  fi
  if [ -n "$right" ]; then
    # shellcheck disable=SC2086 # 刻意按 : 分段
    set -- $right
    nr=$#
    rp="$right"
  fi
  local total=$((nl + nr)) fill=0
  if [ "$comp" -eq 1 ]; then
    fill=$((8 - total))
    [ "$fill" -lt 1 ] && return 1 # "::" 至少补一段；段数溢出同拒
  else
    [ "$total" -ne 8 ] && return 1
  fi
  for t in $lp; do
    case "$t" in "" | *[!0-9a-f]* | ?????*) return 1 ;; esac
    res="$res $((16#$t))"
  done
  i=0
  while [ "$i" -lt "$fill" ]; do
    res="$res 0"
    i=$((i + 1))
  done
  for t in $rp; do
    case "$t" in "" | *[!0-9a-f]* | ?????*) return 1 ;; esac
    res="$res $((16#$t))"
  done
  printf '%s\n' "${res# }"
}

_guard_v6() { # host_lc 含冒号 → 展成 8 hextet 判类；嵌入 v4 形式回查 _guard_v4
  local h="$1" url="$2" hx
  hx="$(_ip6_hextets "$h")" || {
    _guard_deny "$url" "IPv6 字面畸形：$h"
    return 2
  }
  local IFS=' '
  # shellcheck disable=SC2086 # 刻意空格分段
  set -- $hx
  if [ "$#" -ne 8 ]; then
    _guard_deny "$url" "IPv6 展开失败：$h"
    return 2
  fi
  if [ "$(($1 & 65472))" -eq 65152 ]; then # fe80::/10 链路本地
    _guard_deny "$url" "IPv6 link-local fe80::/10"
    return 2
  fi
  if [ "$(($1 & 65024))" -eq 64512 ]; then # fc00::/7 ULA
    _guard_deny "$url" "IPv6 ULA fc00::/7"
    return 2
  fi
  if [ "$(($1 & 65280))" -eq 65280 ]; then # ff00::/8 组播
    _guard_deny "$url" "IPv6 multicast ff00::/8"
    return 2
  fi
  if [ "$(($1 & 65472))" -eq 65216 ]; then # fec0::/10 站点本地（已废形，照拒）
    _guard_deny "$url" "IPv6 site-local fec0::/10"
    return 2
  fi
  if [ "$1" -eq 0 ] && [ "$2" -eq 0 ] && [ "$3" -eq 0 ] && [ "$4" -eq 0 ]; then
    if [ "$5" -eq 0 ] && [ "$6" -eq 0 ]; then
      if [ "$7" -eq 0 ] && [ "$8" -le 1 ]; then
        _guard_deny "$url" "IPv6 未指定/回环 :: / ::1"
        return 2
      fi
      _guard_v4 "$(_v4of "$7" "$8")" "$url" # ::/96 v4-compat（已废形，照查）
      return $?
    fi
    if { [ "$5" -eq 0 ] && [ "$6" -eq 65535 ]; } ||
      { [ "$5" -eq 65535 ] && [ "$6" -eq 0 ]; }; then
      _guard_v4 "$(_v4of "$7" "$8")" "$url" # ::ffff/96 mapped 与 ::ffff:0/96 translated
      return $?
    fi
  fi
  if [ "$1" -eq 8194 ]; then # 6to4 2002::/16：v4 在 hextet2-3
    _guard_v4 "$(_v4of "$2" "$3")" "$url"
    return $?
  fi
  if [ "$1" -eq 100 ] && [ "$2" -eq 65435 ] && [ "$3" -eq 0 ] &&
    [ "$4" -eq 0 ] && [ "$5" -eq 0 ] && [ "$6" -eq 0 ]; then
    _guard_v4 "$(_v4of "$7" "$8")" "$url" # NAT64 WKP 64:ff9b::/96
    return $?
  fi
  if [ "$1" -eq 100 ] && [ "$2" -eq 65435 ] && [ "$3" -eq 1 ]; then
    # NAT64 本地前缀 64:ff9b:1::/48（RFC8215 local-use）：运营商可在前缀内
    # 再切 /56 /64 /96 NSP，内嵌 v4 位置随前缀长漂移——只按 RFC6052 /48 偏移
    # 解码会漏检/误判公网 → 整段拒（对齐 media-get python is_global：非全局一律拒）
    _guard_deny "$url" "IPv6 NAT64 本地前缀 64:ff9b:1::/48"
    return 2
  fi
  if [ "$1" -eq 8193 ] && [ "$2" -eq 0 ]; then # teredo 2001::/32：v4=末 32b XOR ffff
    _guard_v4 "$(_v4of "$((65535 - $7))" "$((65535 - $8))")" "$url"
    return $?
  fi
  if { [ "$5" -eq 0 ] || [ "$5" -eq 512 ]; } && [ "$6" -eq 24318 ]; then
    _guard_v4 "$(_v4of "$7" "$8")" "$url" # ISATAP IID 0000/0200:5efe:v4
    return $?
  fi
  return 0
}
