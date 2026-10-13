#!/bin/bash
# git-format-staged 的 stdin→stdout formatter（见 .pre-commit-config.yaml）。
# shfmt/shellcheck 只认 sh/bash/dash/ksh：shebang 为 zsh 的脚本原样透传，
# 其余按 bash 语法以 2 空格缩进格式化。
set -e
first=
# 空 stdin 时 read 以非零报 EOF——裸 `read` 会被 set -e 放大成整条
# formatter 失败；无换行的末行同样非零返回但 first 里已有内容，照常处理
if ! IFS= read -r first; then
  [[ -z $first ]] && exit 0
fi
case "$first" in
*zsh*) {
  printf '%s\n' "$first"
  cat
} ;;
*) {
  printf '%s\n' "$first"
  cat
} | shfmt -i 2 ;;
esac
