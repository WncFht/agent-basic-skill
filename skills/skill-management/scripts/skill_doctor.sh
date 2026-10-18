#!/usr/bin/env bash
# skill_doctor.sh — 三 CLI 共用 skill/AGENTS.md 体系体检。
#
# 用法：
#   bash skill_doctor.sh [仓库目录 ...]
#
# 不传参数时把 $PWD（若含 .agents/skills）和 ~/Desktop/obsidian 当仓库层检查。
# 退出码：有 FAIL 为 1，否则 0（WARN 不阻塞）。
#
# 检查项：
#   1. 5 条软链存在、是软链、解析到 ~/.agents
#   1b. CC instructionFiles 档位为 claude-md-and-agents-md（~/AGENTS.md 才作全局指令注入）
#   2. 各位置 SKILL.md 的 frontmatter name 与目录名一致
#   3. 跨位置同名 skill（全局/仓库/codex 私有/incubator；incubator 撞名只 WARN，不污染 FAIL）
#   4. 保留名冲突（CC 内置 / codex .system / kimi）
#   5. 仓库 ↔ 全局同名副本内容漂移
#   6. 仓库根 AGENTS.md 与 CLAUDE.md 共存（both 双注入漂移 / fallback 遮蔽全链）
#   7. 仓库有 .agents/skills 但缺 .claude/skills 软链（CC 不可见）
#   8. 全局 skill 带 agents/openai.yaml（跨 harness 界面元数据；缺了 WARN）
#   9. deps.toml 声明的外部依赖齐全（skill_deps.py 复用）

set -u

AGENTS_HOME="$HOME/.agents"
VAULT="$HOME/Desktop/obsidian"

CC_RESERVED="dataviz update-config keybindings-help code-review simplify fewer-permission-prompts loop claude-api workflow-authoring run init security-review"
CODEX_SYSTEM="imagegen openai-docs plugin-creator review-agent skill-creator skill-installer"
KIMI_RESERVED="import-from-cc-codex init mcp-config"

WARN=0
FAIL=0

ok() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
warn() {
  printf '  \033[33mWARN\033[0m %s\n' "$1"
  WARN=$((WARN + 1))
}
fail() {
  printf '  \033[31mFAIL\033[0m %s\n' "$1"
  FAIL=$((FAIL + 1))
}
hdr() { printf '\n== %s ==\n' "$1"; }

# ── 1. 软链 ────────────────────────────────────────────────

check_link() { # $1=链接路径 $2=期望目标（解析后）
  local link="$1" want="$2"
  if [ ! -L "$link" ]; then
    [ -e "$link" ] && fail "$link 存在但不是软链" || fail "$link 缺失"
    return
  fi
  if [ ! -e "$link" ]; then
    fail "$link → $(readlink "$link")（断链）"
  elif [ "$link" -ef "$want" ]; then
    ok "$link → $want"
  else
    fail "$link → $(readlink "$link")（期望 $want）"
  fi
}

hdr "软链"
check_link "$HOME/AGENTS.md" "$AGENTS_HOME/AGENTS.md"
check_link "$HOME/.claude/AGENTS.md" "$AGENTS_HOME/AGENTS.md"
check_link "$HOME/.claude/skills" "$AGENTS_HOME/skills"
check_link "$HOME/.codex/AGENTS.md" "$AGENTS_HOME/AGENTS.md"
check_link "$HOME/.kimi-code/AGENTS.md" "$AGENTS_HOME/AGENTS.md"

# ── 1b. CC 指令文件档位 ────────────────────────────────────

hdr "CC 指令文件档位"
SETTINGS="$HOME/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
  warn "$SETTINGS 缺失——CC 回退默认 fallback 模式，~/AGENTS.md 仅在没有 CLAUDE.md 的项目加载"
elif command -v jq >/dev/null 2>&1; then
  mode="$(jq -r '.pluginConfigs["agents-md@builtin"].options.instructionFiles // empty' "$SETTINGS" 2>/dev/null)"
  if [ "$mode" = "claude-md-and-agents-md" ]; then
    ok "instructionFiles=$mode"
  else
    warn "instructionFiles=${mode:-未设置（默认 fallback）}——~/AGENTS.md 在有自家 CLAUDE.md 的仓库不加载，全局指令覆盖不全"
  fi
else
  warn "无 jq，跳过 instructionFiles 检查"
fi

# ── 仓库集合 ───────────────────────────────────────────────

REPOS=""
if [ $# -gt 0 ]; then
  REPOS="$*"
else
  [ -d "$PWD/.agents/skills" ] && REPOS="$PWD"
  [ -d "$VAULT/.agents/skills" ] && case " $REPOS " in *" $VAULT "*) ;; *) REPOS="$REPOS $VAULT" ;; esac
fi

# ── 2+3+4. skill 清单、frontmatter、撞名 ──────────────────

declare -a ALL_NAMES=() ALL_LOCS=()
collect() { # $1=skills 根 $2=位置标签 $3=严重度（incubator 只 warn）
  [ -d "$1" ] || return 0
  local d name base sev="${3:-fail}"
  # 在当前 shell 校验并收集，避免进程替换的子 shell 丢失 WARN/FAIL 计数。
  for d in "$1"/*/; do
    [ -f "$d/SKILL.md" ] || continue
    name="$(awk -F': *' 'NR == 1 { if ($0 != "---") exit; next } /^---$/ { exit } /^name:/ { gsub(/\r|"/, "", $2); print $2; exit }' "$d/SKILL.md")"
    base="$(basename "$d")"
    if [ -z "$name" ]; then
      "$sev" "${d}SKILL.md 的 frontmatter 无 name 字段"
      name="$base"
    elif [ "$name" != "$base" ]; then
      "$sev" "${d} 目录名 $base 与 frontmatter name $name 不一致"
    fi
    ALL_NAMES+=("$name")
    ALL_LOCS+=("$2")
  done
}

hdr "frontmatter name 检查"
NAME_WARN=$WARN
NAME_FAIL=$FAIL
collect "$AGENTS_HOME/skills" "global"
collect "$AGENTS_HOME/incubator" "incubator" warn
collect "$HOME/.codex/skills" "codex"
collect "$HOME/.codex/skills/.system" "codex-system"
collect "$HOME/.kimi-code/skills" "kimi"
for r in $REPOS; do collect "$r/.agents/skills" "repo:$(basename "$r")"; done
if [ ${#ALL_NAMES[@]} -eq 0 ]; then
  warn "任何位置都没找到 skill"
elif [ "$WARN" -eq "$NAME_WARN" ] && [ "$FAIL" -eq "$NAME_FAIL" ]; then
  ok "${#ALL_NAMES[@]} 个 SKILL.md 的 name 与目录名一致"
fi

hdr "撞名与保留名"
if [ "${#ALL_NAMES[@]}" -gt 0 ]; then
  for i in "${!ALL_NAMES[@]}"; do
    n="${ALL_NAMES[$i]}"
    sev=fail
    [ "${ALL_LOCS[$i]}" = "incubator" ] && sev=warn
    for word in $CC_RESERVED $KIMI_RESERVED; do
      [ "$n" = "$word" ] && "$sev" "${n}（${ALL_LOCS[$i]}）撞 CC/kimi 保留名"
    done
    for word in $CODEX_SYSTEM; do
      [ "$n" = "$word" ] && case "${ALL_LOCS[$i]}" in codex-system | codex-system:*) ;; *) "$sev" "${n}（${ALL_LOCS[$i]}）撞 codex .system 保留名" ;; esac
    done
  done
  # 跨位置同名：按 name 聚合位置，去重后多于一处才报
  for i in "${!ALL_NAMES[@]}"; do
    n="${ALL_NAMES[$i]}"
    [ "$i" -eq 0 ] || case " ${SEEN-} " in *" ${n} "*) continue ;; esac
    locs=""
    for j in "${!ALL_NAMES[@]}"; do
      [ "${ALL_NAMES[$j]}" = "$n" ] || continue
      case " ${locs} " in *" ${ALL_LOCS[$j]} "*) ;; *) locs="${locs} ${ALL_LOCS[$j]}" ;; esac
    done
    set -- $locs
    [ $# -gt 1 ] && warn "${n} 存在于多处：${locs}（codex 双列，kimi/CC 按层级遮蔽）"
    SEEN="${SEEN-} ${n}"
  done
fi

# ── 4b. agents/openai.yaml ────────────────────────────────

hdr "agents/openai.yaml"
OAI_MISSING=0
for d in "$AGENTS_HOME/skills"/*/; do
  [ -f "$d/SKILL.md" ] || continue
  if [ ! -f "$d/agents/openai.yaml" ]; then
    warn "$(basename "$d") 缺 agents/openai.yaml（跨 harness 界面元数据，最小格式见 skill-management 规则 6）"
    OAI_MISSING=$((OAI_MISSING + 1))
  fi
done
[ "$OAI_MISSING" -eq 0 ] && ok "全部全局 skill 带 agents/openai.yaml"

# ── 5. 仓库 ↔ 全局漂移 ────────────────────────────────────

hdr "仓库 ↔ 全局副本漂移"
for r in $REPOS; do
  [ -d "$r/.agents/skills" ] || continue
  for d in "$r/.agents/skills"/*/; do
    base="$(basename "$d")"
    g="$AGENTS_HOME/skills/$base"
    [ -d "$g" ] || continue
    if diff -rq --exclude='.DS_Store' --exclude='__pycache__' --exclude='*.pyc' "$d" "$g" >/dev/null 2>&1; then
      ok "$base 仓库与全局一致"
    else
      warn "${base} 仓库（${r}）与全局副本不一致——以仓库为源时 rsync -a --delete 回拷"
    fi
  done
done

# ── 6+7. 仓库层 ───────────────────────────────────────────

hdr "仓库层"
for r in $REPOS; do
  if [ -f "$r/AGENTS.md" ] && [ -f "$r/CLAUDE.md" ]; then
    # 互链不算共存：任一方是指向对方的软链时仍只有一个事实源
    clink="$(readlink "$r/CLAUDE.md" 2>/dev/null || true)"
    alink="$(readlink "$r/AGENTS.md" 2>/dev/null || true)"
    if [ "$clink" = "AGENTS.md" ] || [ "$alink" = "CLAUDE.md" ]; then
      ok "$r AGENTS.md/CLAUDE.md 互链，单一事实源"
    else
      fail "$r 根目录 AGENTS.md 与 CLAUDE.md 共存（both 模式双注入漂移，fallback 模式遮蔽整条 AGENTS.md 链）"
    fi
  fi
  if [ -d "$r/.agents/skills" ]; then
    if [ -L "$r/.claude/skills" ]; then
      check_link "$r/.claude/skills" "$r/.agents/skills"
    else
      fail "$r 有 .agents/skills 但缺 .claude/skills 软链（CC 看不到仓库 skill）"
    fi
  fi
done
[ -z "$REPOS" ] && printf '  （无仓库层可查，传仓库路径参数可补上）\n'

# ── 9. skill 外部依赖（deps.toml） ────────────────────────

hdr "skill 外部依赖"
DEPS_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skill_deps.py"
if [ ! -f "$DEPS_PY" ]; then
  warn "skill_deps.py 缺失"
elif ! command -v python3 >/dev/null 2>&1; then
  warn "无 python3，跳过 deps 检查"
elif ! python3 -c 'import tomllib' 2>/dev/null; then
  warn "python3 <3.11（无 tomllib），跳过 deps 检查"
else
  python3 "$DEPS_PY" --quiet
  case $? in
  0) ok "deps.toml 声明的依赖齐全" ;;
  1) fail "有必需依赖缺失——python3 $DEPS_PY --install 补齐" ;;
  2) warn "有可选依赖缺失——python3 $DEPS_PY 查看明细" ;;
  esac
fi

# ── 汇总 ──────────────────────────────────────────────────

hdr "汇总"
printf '  %d WARN, %d FAIL\n' "$WARN" "$FAIL"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
