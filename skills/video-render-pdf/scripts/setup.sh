#!/usr/bin/env bash
# video-render-pdf 环境安装脚本（macOS 为主，幂等：已装则跳过）。
# 用法: setup.sh          检查并安装全部依赖
#       setup.sh --check  只验收不安装（等同 doctor.sh）
# 装完跑一次 scripts/doctor.sh 确认全绿。
set -u
cd "$(dirname "$0")/.." || exit 1
SKILL_DIR=$PWD

have() { command -v "$1" >/dev/null 2>&1; }
say() { printf "\033[32m==>\033[0m %s\n" "$1"; }
skip() { printf "    skip %s（已存在）\n" "$1"; }
warn() { printf "\033[33m    ! %s\033[0m\n" "$1"; }

[ "${1:-}" = "--check" ] && exec bash "$SKILL_DIR/scripts/doctor.sh"

# ---------- 1. Homebrew ----------
if ! have brew; then
  warn "需要 Homebrew。先装: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
  exit 1
fi

say "brew formulae"
for f in ffmpeg poppler imagemagick ghostscript tectonic uv; do
  if brew list --formula "$f" >/dev/null 2>&1; then skip "$f"; else
    printf "    install %s ...\n" "$f"
    brew install "$f" || warn "$f 安装失败，稍后可手动 brew install $f"
  fi
done

# ---------- 2. TeX ----------
say "TeX"
if have xelatex; then skip "xelatex"; else
  warn "无 xelatex。最小方案: brew install --cask basictex 后重启终端（或把 /Library/TeX/texbin 加进 PATH）"
fi
if have kpsewhich && ! kpsewhich ctex.sty >/dev/null 2>&1; then
  say "安装 ctex（tlmgr）"
  tlmgr install ctex 2>/dev/null || tlmgr --usermode install ctex || warn "ctex 安装失败: sudo tlmgr install ctex"
else
  have kpsewhich && skip "ctex"
fi
if have kpsewhich && ! kpsewhich FandolSong-Regular.otf >/dev/null 2>&1; then
  say "安装 fandol 中文字体（usermode 免 sudo）"
  tlmgr --usermode init-usertree >/dev/null 2>&1
  tlmgr --usermode install fandol || warn "fandol 失败——编译时可退回 fontset=mac/windows"
else
  have kpsewhich && skip "fandol"
fi

# ---------- 3. 素材获取层（link-get skill） ----------
# yt-dlp / BBDown / JS runtime / Canvas 凭证全归 link-get 车道，本 skill 不重复安装。
say "link-get（素材获取层）"
if [ -f "$HOME/.agents/skills/link-get/scripts/setup.sh" ]; then
  bash "$HOME/.agents/skills/link-get/scripts/setup.sh" || warn "link-get setup 未跑完——下载车道可能缺件"
else
  warn "link-get skill 缺失（路径 ~/.agents/skills/link-get）——克隆 .agents 仓或同步 skills 后重跑"
fi

# ---------- 4. PATH 提醒 ----------
case ":$PATH:" in
*":$HOME/.local/bin:"*) ;;
*) warn "$HOME/.local/bin 不在 PATH 上——BBDown/uv tools 需要它，加进 shell 配置" ;;
esac

say "验收"
exec bash "$SKILL_DIR/scripts/doctor.sh"
