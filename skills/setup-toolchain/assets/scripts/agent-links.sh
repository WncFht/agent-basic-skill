#!/bin/bash
# 重建 Claude Code 的本机入口软链：
#   .claude/skills -> ../.agents/skills        （目录级软链：一条覆盖全部仓库
#   skill，与全局 ~/.claude/skills 同一约定，新增 skill 零维护）
# AGENTS.md 与 .agents/ 是入库的唯一事实源（Claude Code 原生读 AGENTS.md，
# 不再需要 CLAUDE.md 软链）；/.claude/ 整体 gitignore，属本机便利层。
# clone 后或链接损坏时跑一遍本脚本即可恢复。
set -euo pipefail
cd "$(dirname "$0")/.."

# 本脚本按 <repo>/scripts/agent-links.sh 布局定位仓根——直接在事实源
# assets/ 下跑会污染模板目录（造出悬空软链等），AGENTS.md 不在即拒。
[[ -f AGENTS.md ]] || {
  echo "error: $(pwd) 没有 AGENTS.md——脚本应拷进目标仓 scripts/ 后再跑" >&2
  exit 1
}

# 旧版脚本建的 CLAUDE.md -> AGENTS.md 软链顺手清掉；实体 CLAUDE.md 不碰
if [[ -L CLAUDE.md && $(readlink CLAUDE.md) == AGENTS.md ]]; then
  rm CLAUDE.md
  echo "removed: stale CLAUDE.md symlink"
fi

mkdir -p .claude .agents/skills

skills_link=.claude/skills
want="../.agents/skills"
agents_abs=$(cd .agents/skills && pwd -P)

if [[ -L $skills_link ]]; then
  # 已是软链：确认解析进本仓 .agents/skills；悬空或指别处的链报出来手工处置
  if [[ -d $skills_link && "$(cd "$skills_link" && pwd -P)" == "$agents_abs" ]]; then
    : # 已是解析到本仓 .agents/skills 的目录级软链
  else
    echo "error: $skills_link 是指向别处的软链：$(readlink "$skills_link")（期望 $want）" >&2
    exit 1
  fi
elif [[ -d $skills_link ]]; then
  # 旧式逐 skill 软链农场自动升级成目录级：可覆盖项 = 指向 ../../.agents/skills/*
  # 的软链与可丢弃的 .DS_Store；混有实体目录或外来软链时拒绝，先手工处置
  shopt -s nullglob dotglob
  blockers=()
  for entry in "$skills_link"/*; do
    base=${entry##*/}
    if [[ $base == .DS_Store ]]; then
      continue
    elif [[ -L $entry ]]; then
      dest=$(readlink "$entry")
      case $dest in
      ../../.agents/skills/*) ;; # 本仓 skill 软链的规范相对形式，目录级等价覆盖
      *)
        # 其它写法（绝对路径、错深度的 ../.agents/...）只认解析后确实落进
        # 本仓 .agents/skills 的；悬空或外来软链一律进 blockers 手工处置
        if [[ $dest == /* ]]; then
          resolved=$(cd "$(dirname "$dest")" 2>/dev/null && pwd -P || true)
        else
          resolved=$(cd "${entry%/*}/$(dirname "$dest")" 2>/dev/null && pwd -P || true)
        fi
        if [[ $resolved == "$agents_abs" ]]; then
          :
        else
          blockers+=("$entry -> $dest")
        fi
        ;;
      esac
    else
      blockers+=("$entry")
    fi
  done
  if ((${#blockers[@]})); then
    printf 'error: %s 是实体目录且含非本仓 skill 条目，拒绝覆盖：\n' "$skills_link" >&2
    printf '  %s\n' "${blockers[@]}" >&2
    echo "       把实体 skill 迁进 .agents/skills/ 后再跑本脚本" >&2
    exit 1
  fi
  rm -f "$skills_link"/* # 逐 skill 软链 + .DS_Store
  rmdir "$skills_link"
  ln -s "$want" "$skills_link"
elif [[ -e $skills_link ]]; then
  echo "error: $skills_link 是实体文件（非目录/软链），拒绝覆盖" >&2
  exit 1
else
  ln -s "$want" "$skills_link"
fi

echo "linked: .claude/skills -> $want"
