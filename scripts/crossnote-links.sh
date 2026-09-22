#!/bin/bash
# 重建 MPE 预览环境（.crossnote）的本机链接层：
#   .crossnote/{parser.js,style.less,config.js,head.html,README.md} -> $CROSSNOTE_SRC/*
#   .crossnote/{scripts,tests,vendor} -> $CROSSNOTE_SRC/*（目录级软链）
#   .crossnote/{pseudocode-runtime.js,theme-toggle.js} == 与事实源同 inode 的硬链
#
# 为什么混合链接：crossnote 加载 config/parser/style/head 走 fs.readFile
# 跟软链、不做边界检查；而经 @import 注入预览的 .js（pseudocode-runtime、
# theme-toggle）要过 isPathInsideProjectDirectory 的 realpathSync 校验——
# 指到 workspace 外的软链会被拒，硬链同 inode 才算"仓内实体文件"。
#
# $CROSSNOTE_SRC 是唯一事实源（默认 setup-toolchain skill 的载荷目录，
# ~/.agents 仓跟踪——改任一仓的软链文件 = 直接改它，各仓即时同步）。
# 已知软肋：编辑器原子保存（写临时文件再 rename）换 inode → 硬链变陈旧
# ——内容分歧时重跑本脚本重建即可。clone 后或链接损坏同样跑一遍。
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${CROSSNOTE_SRC:-$HOME/.agents/skills/setup-toolchain/assets/.crossnote}"
[[ -d $SRC ]] || {
  echo "error: crossnote 事实源不存在: $SRC（可用 CROSSNOTE_SRC= 改指）" >&2
  exit 1
}
for f in parser.js style.less config.js head.html pseudocode-runtime.js theme-toggle.js; do
  [[ -f $SRC/$f ]] || {
    echo "error: 事实源缺文件: $SRC/$f" >&2
    exit 1
  }
done

mkdir -p .crossnote

# 可软链项（配置四件套 + 说明 + 构建/测试工具目录）
for item in parser.js style.less config.js head.html README.md scripts tests vendor; do
  dest=".crossnote/$item"
  if [[ -e $dest && ! -L $dest ]]; then
    echo "error: $dest 是实体文件/目录（仓内定制或待迁移副本），拒绝覆盖——" >&2
    echo "       要分叉就保留它；要回同步就删掉重跑本脚本" >&2
    exit 1
  fi
  ln -sfn "$SRC/$item" "$dest"
done

# 经 @import 注入预览的 .js 只能硬链：同 inode 才过 realpath 边界检查
for name in pseudocode-runtime.js theme-toggle.js; do
  rt=".crossnote/$name"
  if [[ -L $rt ]]; then
    rm "$rt" # 软链必被边界检查拒，直接转硬链
    ln "$SRC/$name" "$rt"
  elif [[ ! -e $rt ]]; then
    ln "$SRC/$name" "$rt"
  elif [[ $rt -ef $SRC/$name ]]; then
    : # 已是同 inode，无操作
  elif cmp -s "$SRC/$name" "$rt"; then
    rm "$rt" # 内容一致的实体副本：转硬链
    ln "$SRC/$name" "$rt"
  else
    echo "error: $rt 是实体文件且与事实源内容分歧，拒绝覆盖——" >&2
    echo "       保留分叉则不管；回同步就删掉重跑本脚本" >&2
    exit 1
  fi
done

echo "linked: .crossnote/* -> $SRC"'（runtime js 为硬链）'
