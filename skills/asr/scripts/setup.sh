#!/usr/bin/env bash
# setup.sh — bootstrap the asr skill on a fresh machine:
#   .venv/ (uv; sherpa-onnx + numpy) and models/ (silero VAD + per-lane ASR).
#
#   bash scripts/setup.sh                        # both lanes, auto channel
#   bash scripts/setup.sh --lang en              # EN lane only
#   bash scripts/setup.sh --source modelscope    # force a download channel
#   bash scripts/setup.sh --lang vad --gpu zh    # VAD + zh GPU tier only
#   bash scripts/setup.sh --gpu all              # everything + both GPU tiers
#
# Channels: auto probes hf / modelscope / github and, per artifact, tries
# every channel that carries it — reachable first. Downloads resume via
# <file>.part (curl -C -) and are size- and sha256-checked when the channel
# advertises them. Lane models (fp32) exist only on hf; modelscope/github
# cover VAD and the GPU artifacts (gguf, Qwen). Env hooks for rough networks:
#   HF_ENDPOINT   hf base url override (huggingface_hub convention) — point
#                 at any mirror that serves /api and /resolve paths
#   ASR_GH_PROXY  url prefix for github.com, e.g. https://ghproxy.net/ —
#                 github release CDNs are often blocked while the site itself
#                 loads; verified-live prefixes 2026-09: ghproxy.net,
#                 ghfast.top, gh-proxy.com (community proxies, opt-in)
# --gpu en|zh|all adds the GPU tier: en = parakeet-cli bundle (github
# release; linux-x64 cuda / macos-arm64 metal) + tdt gguf (hf/modelscope);
# zh = .venv-qwen + Qwen3 models (hf/modelscope, CUDA-only — skipped on
# macOS). GPU artifacts are downloads/venvs only — no GPU needed at setup
# time.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SKILL=$(cd "$HERE/.." && pwd)
VENV="$SKILL/.venv"
MODELS="${ASR_MODELS:-$SKILL/models}"

LANGS=both
SRC=auto
GPU=none
while [ $# -gt 0 ]; do
  case "$1" in
  --lang)
    LANGS=${2:?"--lang needs en|zh|both|vad"}
    shift 2
    ;;
  --source)
    SRC=${2:?"--source needs auto|hf|modelscope|github"}
    shift 2
    ;;
  --models-dir)
    MODELS=${2:?}
    shift 2
    ;;
  --gpu)
    GPU=${2:?"--gpu needs en|zh|all"}
    shift 2
    ;;
  -h | --help)
    sed -n '2,12p' "$0"
    exit 0
    ;;
  *)
    echo "error: unknown arg: $1" >&2
    exit 2
    ;;
  esac
done
case "$LANGS" in en | zh | both | vad) ;; *)
  echo "error: --lang must be en|zh|both|vad" >&2
  exit 2
  ;;
esac
case "$GPU" in en | zh | all | none) ;; *)
  echo "error: --gpu must be en|zh|all" >&2
  exit 2
  ;;
esac

# ----------------------------------------------------------------- venv
# uv only — auto-install via the official script when missing
if ! command -v uv >/dev/null 2>&1; then
  echo "[setup] uv not found — installing via astral.sh"
  curl -fsSL https://astral.sh/uv/install.sh | sh
  for d in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    [ -x "$d/uv" ] && PATH="$d:$PATH"
  done
fi
command -v uv >/dev/null 2>&1 || {
  echo "error: uv missing and auto-install failed —" \
    "see https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}
pip_install() { uv pip install --python "$VENV/bin/python" "$@"; }
[ -x "$VENV/bin/python" ] || {
  uv venv --clear --python 3.12 "$VENV" 2>/dev/null || uv venv --clear "$VENV"
}
PY="$VENV/bin/python"
pip_install -q sherpa-onnx numpy

command -v ffmpeg >/dev/null 2>&1 || echo \
  "note: ffmpeg not found — needed for non-wav input (mp4/m4a/mp3/...)"

# -------------------------------------------------------------- channel
HF_BASE=${HF_ENDPOINT:-https://huggingface.co}
GH_PROXY=${ASR_GH_PROXY:-}
[ -n "$GH_PROXY" ] && GH_PROXY="${GH_PROXY%/}/" # tolerate missing tail slash

probe() { curl -fs -m 6 -o /dev/null "$1" 2>/dev/null; }
# release assets redirect to objects.githubusercontent.com — often blocked
# even when github.com itself loads, so probe a real asset, not the homepage
probe_gh() { curl -fsL -m 10 -o /dev/null -r 0-0 "$1" 2>/dev/null; }

ok_hf=0 ok_ms=0 ok_gh=0
probe "$HF_BASE/api/models/csukuangfj/sherpa-doc-files" && ok_hf=1
probe "https://modelscope.cn/api/v1/models/liaowenbin/silero_vad" && ok_ms=1
gh_probe="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad_v5.onnx"
if [ -n "$GH_PROXY" ]; then
  probe_gh "$GH_PROXY$gh_probe" && ok_gh=1
  [ "$ok_gh" = 0 ] && probe_gh "$gh_probe" && ok_gh=1
else
  probe_gh "$gh_probe" && ok_gh=1
fi

chan_ok() {
  case "$1" in
  hf) [ "$ok_hf" = 1 ] ;;
  modelscope) [ "$ok_ms" = 1 ] ;;
  github) [ "$ok_gh" = 1 ] ;;
  esac
}

if [ "$SRC" = auto ]; then
  CHANS=""
  for c in hf modelscope github; do chan_ok "$c" && CHANS="$CHANS $c"; done
  # unreachable channels stay as last resort — a failed probe may lie
  for c in hf modelscope github; do chan_ok "$c" || CHANS="$CHANS $c"; done
else
  case "$SRC" in hf | modelscope | github) ;; *)
    echo "error: --source must be auto|hf|modelscope|github" >&2
    exit 2
    ;;
  esac
  CHANS=" $SRC"
fi
echo "[setup] source=$SRC chans='${CHANS# }' hf_ok=$ok_hf ms_ok=$ok_ms" \
  "gh_ok=$ok_gh lang=$LANGS gpu=$GPU models=$MODELS"
[ "$HF_BASE" != "https://huggingface.co" ] && echo "[setup] HF_ENDPOINT=$HF_BASE"
[ -n "$GH_PROXY" ] && echo "[setup] ASR_GH_PROXY=$GH_PROXY"

# GPU-tier channel guard: gguf and Qwen repos live on hf + modelscope only.
if [ "$GPU" != none ] && [ "$SRC" = github ]; then
  echo "error: --gpu weights (gguf/Qwen) are not on github —" \
    "use --source hf|modelscope" >&2
  exit 1
fi

# ------------------------------------------------------------- download
mkdir -p "$MODELS"

# BSD wc right-pads with spaces ("    123") — strip whitespace or every
# size comparison breaks on macOS
fsize() { wc -c <"$1" 2>/dev/null | tr -d '[:space:]'; }
sha_ok() { # file expected — empty expected passes
  [ -n "$2" ] || return 0
  if command -v sha256sum >/dev/null 2>&1; then
    echo "$2  $1" | sha256sum -c - >/dev/null 2>&1
  else
    echo "$2  $1" | shasum -a 256 -c - >/dev/null 2>&1
  fi
}

# fetch url dest [size] [sha256] [tries] — resumable: writes dest.part,
# resumes it on retry (each retry re-follows redirects so signed CDN urls
# refresh), verifies size+sha256, then renames into place.
fetch() {
  url=$1 dest=$2 size=${3:-0} sha=${4:-} tries=${5:-3}
  part="$dest.part"
  if [ -f "$dest" ] && { [ "$size" -le 0 ] || [ "$(fsize "$dest")" = "$size" ]; }; then
    sha_ok "$dest" "$sha" && return 0
    rm -f "$dest"
  fi
  mkdir -p "$(dirname "$dest")"
  i=0
  while [ "$i" -lt "$tries" ]; do
    i=$((i + 1))
    # .part may already be complete from an interrupted run
    if [ -f "$part" ] && [ "$size" -gt 0 ] && [ "$(fsize "$part")" = "$size" ]; then
      rc=0
    elif [ -f "$part" ]; then
      code=$(curl -fsSL -C - --connect-timeout 10 --speed-limit 10240 --speed-time 30 \
        -w '%{http_code}' -o "$part" "$url") && rc=0 || rc=$?
      if [ "$rc" != 0 ] && [ "$code" = 416 ]; then
        rc=0                    # range past EOF — .part was already complete
      elif [ "$rc" = 33 ]; then # server can't range — restart whole file
        rm -f "$part"
        curl -fsSL --connect-timeout 10 --speed-limit 10240 --speed-time 30 \
          -o "$part" "$url" && rc=0 || rc=$?
      fi
    else
      curl -fsSL --connect-timeout 10 --speed-limit 10240 --speed-time 30 \
        -o "$part" "$url" && rc=0 || rc=$?
    fi
    if [ "$rc" = 0 ]; then
      if [ "$size" -gt 0 ] && [ "$(fsize "$part")" != "$size" ]; then
        echo "[dl] short file ($url) — keeping .part for resume" >&2
        sleep 2
        continue
      fi
      if ! sha_ok "$part" "$sha"; then
        echo "[dl] sha256 mismatch: $url" >&2
        rm -f "$part"
        sleep 2
        continue
      fi
      mv -f "$part" "$dest"
      return 0
    fi
    [ "$i" -lt "$tries" ] && sleep $((i * 2))
  done
  return 1
}

resolve_url() { # channel repo path
  case "$1" in
  hf) echo "$HF_BASE/$2/resolve/main/$3" ;;
  modelscope) echo "https://modelscope.cn/models/$2/resolve/master/$3" ;;
  esac
}

# list_files channel repo — "path\tsize\tsha256" per blob. hf sha256 comes
# from lfs.oid (absent for small non-lfs blobs), modelscope from Sha256.
list_files() {
  case "$1" in
  hf)
    curl -fs -m 20 "$HF_BASE/api/models/$2/tree/main?recursive=true" |
      "$PY" -c 'import json,sys
for e in json.load(sys.stdin):
    if e["type"] != "file":
        continue
    print(e["path"], e.get("size") or 0, (e.get("lfs") or {}).get("oid", ""), sep="\t")'
    ;;
  modelscope)
    curl -fs -m 20 "https://modelscope.cn/api/v1/models/$2/repo/files?Recursive=true" |
      "$PY" -c 'import json,sys
for e in json.load(sys.stdin)["Data"]["Files"]:
    if e["Type"] != "blob":
        continue
    print(e["Path"], e.get("Size") or 0, e.get("Sha256") or "", sep="\t")'
    ;;
  esac
}

# pull_any dest include-re chan:repo ... — whole-repo download with
# per-file fallback across channels: union of each reachable repo's file
# list, every file tried on each channel that carries it until one sticks.
# fp32 keeps weights in .weights sidecars next to the .onnx, so grab every
# blob matching include-re; test_wavs/.gitattributes/README always skipped.
pull_any() {
  dst=$1 inc=$2
  shift 2
  tdir=$(mktemp -d "${TMPDIR:-/tmp}/asr-pull.XXXXXX")
  chans_used=""
  for cr in "$@"; do
    c=${cr%%:*} r=${cr#*:}
    case " $CHANS " in *" $c "*) ;; *) continue ;; esac
    if list_files "$c" "$r" >"$tdir/$c.tsv" 2>/dev/null && [ -s "$tdir/$c.tsv" ]; then
      echo "$r" >"$tdir/$c.repo"
      chans_used="$chans_used $c"
    else
      echo "[dl] cannot list $r on $c" >&2
    fi
  done
  if [ -z "$chans_used" ]; then
    rm -rf "$tdir"
    return 1
  fi
  for c in $chans_used; do cut -f1 "$tdir/$c.tsv"; done |
    grep -vE '^(test_wavs/|\.gitattributes$|README\.md$)' | grep -E "$inc" |
    awk '!seen[$0]++' >"$tdir/paths"
  if [ ! -s "$tdir/paths" ]; then
    rm -rf "$tdir"
    return 1
  fi
  fail=0
  while IFS= read -r p; do
    dest="$dst/$p"
    got=0
    for c in $chans_used; do
      meta=$(awk -F'\t' -v p="$p" '$1==p {print; exit}' "$tdir/$c.tsv")
      [ -n "$meta" ] || continue
      s=$(printf '%s' "$meta" | cut -f2)
      if [ -f "$dest" ] && { [ "${s:-0}" -le 0 ] || [ "$(fsize "$dest")" = "$s" ]; }; then
        got=1
        break
      fi
    done
    if [ "$got" = 0 ]; then
      for c in $chans_used; do
        meta=$(awk -F'\t' -v p="$p" '$1==p {print; exit}' "$tdir/$c.tsv")
        [ -n "$meta" ] || continue
        s=$(printf '%s' "$meta" | cut -f2)
        h=$(printf '%s' "$meta" | cut -f3)
        url=$(resolve_url "$c" "$(cat "$tdir/$c.repo")" "$p")
        chan_ok "$c" && t=3 || t=1
        echo "[dl] $p ($c)"
        fetch "$url" "$dest" "${s:-0}" "${h:-}" "$t" && {
          got=1
          break
        }
      done
    fi
    [ "$got" = 1 ] || {
      fail=1
      echo "[dl] FAILED on all channels: $p" >&2
    }
  done <"$tdir/paths"
  rm -rf "$tdir"
  [ "$fail" = 0 ]
}

# gh_urls path — candidate urls for a github.com path: proxy first when
# ASR_GH_PROXY is set (user opted in because direct is broken), then direct.
gh_urls() {
  u="https://github.com/$1"
  if [ -n "$GH_PROXY" ]; then
    printf '%s\n%s\n' "$GH_PROXY$u" "$u"
  else
    printf '%s\n' "$u"
  fi
}

# tar_pull dest marker-file url... — fetch a tarball (resumable), untar,
# normalize a single top dir onto dest. marker-file must exist after
# extraction for the pull to count as success.
tar_pull() {
  dst=$1 marker=$2
  shift 2
  [ -e "$dst/$marker" ] && {
    echo "[setup] $dst present, skip"
    return 0
  }
  tmp="$(dirname "$dst")/.tar-pull.$$"
  ok=0
  for url in "$@"; do
    rm -rf "$tmp"
    mkdir -p "$tmp/x"
    echo "[dl] $url"
    if fetch "$url" "$tmp/pkg.tar" 0 "" 2 && tar -xf "$tmp/pkg.tar" -C "$tmp/x" 2>/dev/null; then
      entries=$(find "$tmp/x" -mindepth 1 -maxdepth 1)
      if [ "$(printf '%s\n' "$entries" | wc -l | tr -d '[:space:]')" = 1 ] && [ -d "$entries" ]; then
        rm -rf "${dst:?}"
        mv "$entries" "$dst"
      else
        mkdir -p "$dst"
        for e in $entries; do mv "$e" "$dst/"; done
      fi
      if [ -e "$dst/$marker" ]; then
        ok=1
        break
      fi
      echo "[dl] extracted but no $marker inside: $url" >&2
    fi
  done
  rm -rf "$tmp"
  [ "$ok" = 1 ]
}

# silero VAD — canonical file is the GitHub release asset; hf/modelscope
# carry onnx-community's onnx/model.onnx (an older export — sherpa
# auto-detects its window, verified working) and liaowenbin's modelscope
# copy (512-window export, verified loads). sha256 pinned for all three.
VAD_DIR="$MODELS/silero-vad-v5"
mkdir -p "$VAD_DIR"
if [ -f "$VAD_DIR/silero_vad.onnx" ]; then
  echo "[setup] silero_vad present, skip"
else
  vad_done=0
  # canonical file lives on github — prefer it while reachable
  if chan_ok github; then VCHANS="github"; else VCHANS=""; fi
  # shellcheck disable=SC2086 # VCHANS/CHANS 是空格分隔通道列表，要的就是分词
  VCHANS=$(printf '%s\n' $VCHANS $CHANS github | awk '!s[$0]++')
  for c in $VCHANS; do
    case "$c" in
    github)
      for u in $(gh_urls "k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad_v5.onnx"); do
        echo "[dl] silero_vad.onnx ($u)"
        fetch "$u" "$VAD_DIR/silero_vad.onnx" 0 \
          6b99cbfd39246b6706f98ec13c7c50c6b299181f2474fa05cbc8046acc274396 2 &&
          vad_done=1 && break
      done
      ;;
    hf | modelscope)
      echo "[dl] silero_vad.onnx ($c onnx-community)"
      fetch "$(resolve_url "$c" onnx-community/silero-vad onnx/model.onnx)" \
        "$VAD_DIR/silero_vad.onnx" 0 \
        a4a068cd6cf1ea8355b84327595838ca748ec29a25bc91fc82e6c299ccdc5808 3 &&
        vad_done=1
      ;;
    esac
    [ "$vad_done" = 1 ] && break
  done
  # last resort: liaowenbin's modelscope copy (different export, still loads)
  if [ "$vad_done" = 0 ] && chan_ok modelscope; then
    echo "[dl] silero_vad.onnx (modelscope liaowenbin)"
    fetch \
      "https://modelscope.cn/models/liaowenbin/silero_vad/resolve/master/silero_vad.onnx" \
      "$VAD_DIR/silero_vad.onnx" 0 \
      9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6 3 &&
      vad_done=1
  fi
  [ "$vad_done" = 1 ] || {
    echo "error: silero VAD download failed on every channel" >&2
    exit 1
  }
fi

# lane models — dir names match the sherpa-onnx release convention;
# transcribe.py resolves the same names
lane() { [ "$LANGS" = both ] || [ "$LANGS" = "$1" ]; }

EN_NAME=sherpa-onnx-nemo-parakeet-tdt-0.6b-v2
ZH_NAME=sherpa-onnx-fire-red-asr2-ctc-zh_en-2026-02-25

# Lane models are fp32 sherpa-onnx releases — hf-only on every public
# channel (modelscope/github carry only int8 copies, which this skill
# does not use).
if [ "$SRC" != auto ] && [ "$SRC" != hf ] && [ "$LANGS" != vad ]; then
  echo "error: lane models exist only on HuggingFace —" \
    "use --source hf, or set HF_ENDPOINT to a mirror" >&2
  exit 1
fi

if lane en; then
  pull_any "$MODELS/$EN_NAME" '.' "hf:csukuangfj/$EN_NAME" || {
    echo "error: EN lane ($EN_NAME) failed on every channel" >&2
    [ "$ok_hf" = 0 ] && echo \
      "hint: fp32 needs huggingface.co — unreachable; fix connectivity" \
      "or set HF_ENDPOINT to a mirror" >&2
    exit 1
  }
fi
if lane zh; then
  pull_any "$MODELS/$ZH_NAME" '.' "hf:csukuangfj2/$ZH_NAME" || {
    echo "error: ZH lane ($ZH_NAME) failed on every channel" >&2
    [ "$ok_hf" = 0 ] && echo \
      "hint: fp32 needs huggingface.co — unreachable; fix connectivity" \
      "or set HF_ENDPOINT to a mirror" >&2
    exit 1
  }
fi

# ---------------------------------------------------------------- gpu tier
# --gpu en|zh|all — GPU artifacts only; safe to install without a GPU.
gpu_lane() { [ "$GPU" = all ] || [ "$GPU" = "$1" ]; }

if [ "$GPU" != none ] && [ "$(uname -s)" = Linux ]; then
  command -v nvidia-smi >/dev/null 2>&1 || echo \
    "note: nvidia-smi not found — installing GPU artifacts anyway" \
    "(needed at run time, not setup time)"
fi

# --gpu en: parakeet-cli bundle (github release, ~700MB; linux = cuda with
# bundled cudart13/cublas RUNPATH=$ORIGIN, macOS arm64 = metal) +
# tdt-0.6b-v2-f16 gguf (~1.3GB). No en GPU bundle exists for other
# platform/arch combos — sherpa CPU is the lane there.
case "$(uname -s):$(uname -m)" in
Linux:x86_64) CPP_BUNDLE=parakeet-v0.5.0-bin-linux-cuda-x64 ;;
Darwin:arm64) CPP_BUNDLE=parakeet-v0.5.0-bin-macos-metal-arm64 ;;
*) CPP_BUNDLE="" ;;
esac
BIN_DIR="$SKILL/bin/$CPP_BUNDLE"
GGUF_DIR="$MODELS/parakeet-cpp-gguf"
GGUF="$GGUF_DIR/tdt-0.6b-v2-f16.gguf"
if gpu_lane en; then
  if [ -z "$CPP_BUNDLE" ]; then
    echo "error: no parakeet-cli GPU bundle for $(uname -s)/$(uname -m) —" \
      "en lane on this machine is sherpa CPU" >&2
    exit 1
  fi
  # shellcheck disable=SC2046 # helpers emit one url per word on purpose
  tar_pull "$BIN_DIR" parakeet-cli \
    $(gh_urls "mudler/parakeet.cpp/releases/download/v0.5.0/$CPP_BUNDLE.tar.gz") || {
    echo "error: parakeet-cli bundle download failed — github release" \
      "assets unreachable; set ASR_GH_PROXY (e.g. https://ghproxy.net/)" >&2
    exit 1
  }
  if [ -f "$GGUF" ]; then
    echo "[setup] gguf present, skip"
  else
    pull_any "$GGUF_DIR" '^tdt-0\.6b-v2-f16\.gguf$' \
      hf:mudler/parakeet-cpp-gguf modelscope:mudler/parakeet-cpp-gguf || {
      echo "error: gguf download failed" >&2
      exit 1
    }
  fi
fi

# --gpu zh: two runtimes over the same model dirs — linux gets .venv-qwen
# (pinned stack — transformers must stay 4.x for qwen_asr 0.0.6), macOS
# arm64 gets .venv-mlx (mlx-qwen3-asr, an MLX reimplementation that loads
# the vanilla Qwen safetensors repos directly). Intel Macs have no qwen
# runtime at all — zh there is sherpa CPU only.
qwen_rt=1
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" != arm64 ]; then
  qwen_rt=0
fi
if gpu_lane zh && [ "$qwen_rt" = 0 ]; then
  echo "note: no qwen runtime for $(uname -s)/$(uname -m) —" \
    "zh lane here is sherpa CPU"
fi
if gpu_lane zh && [ "$qwen_rt" = 1 ]; then
  for m in Qwen3-ASR-1.7B Qwen3-ForcedAligner-0.6B; do
    pull_any "$MODELS/$m" '.' "hf:Qwen/$m" "modelscope:Qwen/$m" || {
      echo "error: $m download failed" >&2
      exit 1
    }
  done
  if [ "$(uname -s)" = Darwin ]; then
    VMLX="$SKILL/.venv-mlx"
    [ -x "$VMLX/bin/python" ] || {
      uv venv --clear --python 3.12 "$VMLX" 2>/dev/null || uv venv --clear "$VMLX"
    }
    # sherpa-onnx+numpy: VAD stage of transcribe.py needs them regardless of backend
    uv pip install --python "$VMLX/bin/python" -q \
      sherpa-onnx numpy "mlx-qwen3-asr[aligner]"
  else
    VQWEN="$SKILL/.venv-qwen"
    [ -x "$VQWEN/bin/python" ] || {
      uv venv --clear --python 3.12 "$VQWEN" 2>/dev/null || uv venv --clear "$VQWEN"
    }
    uv pip install --python "$VQWEN/bin/python" -q \
      sherpa-onnx numpy \
      torch==2.14.0 transformers==4.57.6 accelerate==1.12.0 \
      qwen_asr==0.0.6 qwen_omni_utils==0.0.9
  fi
fi

echo "[setup] done. Transcribe with:"
echo "  $PY $SKILL/scripts/transcribe.py INPUT --lang <en|zh> --out out.srt"
if gpu_lane en; then
  echo "  # en GPU: same command (auto backend) or --backend parakeet_cpp"
fi
if gpu_lane zh && [ "$qwen_rt" = 1 ]; then
  if [ "$(uname -s)" = Darwin ]; then
    echo "  $VMLX/bin/python $SKILL/scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt"
  else
    echo "  $VQWEN/bin/python $SKILL/scripts/transcribe.py INPUT --lang zh --backend qwen --out out.srt"
  fi
fi
if [ "$MODELS" != "$SKILL/models" ]; then
  echo "  (pass --models-dir $MODELS or export ASR_MODELS=$MODELS)"
fi
