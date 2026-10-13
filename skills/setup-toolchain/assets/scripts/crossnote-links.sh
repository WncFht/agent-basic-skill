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
# 已知软肋：编辑器原子保存与 pre-commit 格式化回写（gfs 写临时再 rename）
# 都换 inode → 硬链变陈旧——内容分歧时重跑本脚本重建即可。clone 后或链接
# 损坏同样跑一遍。
set -euo pipefail
cd "$(dirname "$0")/.."

# 与 agent-links.sh 同一约定：按 <repo>/scripts/ 布局定位仓根——直接在事实源
# assets/ 下跑会把链接农场建进模板目录，仓根标志不在即拒。
[[ -f AGENTS.md || -d .git ]] || {
  echo "error: $(pwd) 不是仓根（无 AGENTS.md/.git）——脚本应拷进目标仓 scripts/ 后再跑" >&2
  exit 1
}

SRC="${CROSSNOTE_SRC:-$HOME/.agents/skills/setup-toolchain/assets/.crossnote}"
[[ -d $SRC ]] || {
  echo "error: crossnote 事实源不存在: $SRC（可用 CROSSNOTE_SRC= 改指）" >&2
  exit 1
}
for f in parser.js style.less config.js head.html README.md pseudocode-runtime.js theme-toggle.js; do
  [[ -f $SRC/$f ]] || {
    echo "error: 事实源缺文件: $SRC/$f" >&2
    exit 1
  }
done
for d in scripts tests vendor; do
  [[ -d $SRC/$d ]] || {
    echo "error: 事实源缺目录: $SRC/$d" >&2
    exit 1
  }
done

# 硬链要求本仓与事实源同文件系统——跨设备要到 ln 才炸 EXDEV，提前比 device
# id 把话说清楚（GNU stat -c；BSD/macOS stat -f）。
src_dev=$(stat -c %d "$SRC" 2>/dev/null || stat -f %d "$SRC")
repo_dev=$(stat -c %d . 2>/dev/null || stat -f %d .)
[[ $src_dev == "$repo_dev" ]] || {
  echo "error: 事实源与本仓不在同一文件系统（dev $src_dev vs $repo_dev）——" >&2
  echo "       pseudocode-runtime.js/theme-toggle.js 无法硬链；" >&2
  echo "       把 CROSSNOTE_SRC 指到同盘副本再跑" >&2
  exit 1
}

mkdir -p .crossnote

# MPE 0.8.36 自动填充的默认 stub（打包态 extension.js 实证）：`.crossnote/`
# 目录已存在而文件缺失/不可读时原地写这些固定内容——是纯 filler 不是仓内
# 定制，内容与 stub 一致即可安全转软链；stub 随 MPE 改版会变，那时退化为
# 原有的拒绝覆盖（安全侧）。
mpe_stub() {
  case $1 in
  parser.js)
    cat <<'STUB'
({
  // Please visit the URL below for more information:
  // https://shd101wyy.github.io/markdown-preview-enhanced/#/extend-parser

  onWillParseMarkdown: async function(markdown) {
    return markdown;
  },

  onDidParseMarkdown: async function(html) {
    return html;
  },
})
STUB
    ;;
  config.js)
    cat <<'STUB'
({
  katexConfig: {
  "macros": {}
},

  mathjaxConfig: {
  "tex": {},
  "options": {},
  "loader": {}
},

  mermaidConfig: {
  "startOnLoad": false
},
})
STUB
    ;;
  head.html)
    cat <<'STUB'
<!-- The content below will be included at the end of the <head> element. -->
<script type="text/javascript">
  document.addEventListener("DOMContentLoaded", function () {
    // your code here
  });
</script>
STUB
    ;;
  style.less)
    cat <<'STUB'

/* Please visit the URL below for more information: */
/*   https://shd101wyy.github.io/markdown-preview-enhanced/#/customize-css */

.markdown-preview.markdown-preview {
  // modify your style here
  // eg: background-color: blue;
}
STUB
    ;;
  *) return 1 ;;
  esac
}

# 可软链项（配置四件套 + 说明 + 构建/测试工具目录）
for item in parser.js style.less config.js head.html README.md scripts tests vendor; do
  dest=".crossnote/$item"
  if [[ -e $dest && ! -L $dest ]]; then
    # stub 比对忽略全部空白——编辑器顺手 trim 行尾空白不该算"仓内定制"
    if [[ -f $dest ]] && stub=$(mpe_stub "$item") &&
      [[ $(tr -d '[:space:]' <<<"$stub") == "$(tr -d '[:space:]' <"$dest")" ]]; then
      rm "$dest" # MPE 自动 stub（预览先于建农场打开过），转软链
    else
      echo "error: $dest 是实体文件/目录（仓内定制或待迁移副本），拒绝覆盖——" >&2
      echo "       要分叉就保留它；要回同步就删掉重跑本脚本" >&2
      exit 1
    fi
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

# 全局层体检：~/.local/state/crossnote/style.less 应是指向事实源的活软链——
# 全局与仓库 style.less 同源时 extension.js 的 globalCss dedupe 才走单份分支。
# 软链 dangling 时 MPE 读失败会原地回写 ~235B 默认 stub——写穿软链就是直接
# 覆盖事实源，所以这里对非活链报 error；实体文件（含 MPE 写的 stub）只 warn，
# 全局层是机器状态不属仓内容，不动手替换。
GLOBAL_STYLE="$HOME/.local/state/crossnote/style.less"
if [[ -L $GLOBAL_STYLE ]]; then
  if [[ $GLOBAL_STYLE -ef $SRC/style.less ]]; then
    echo "global: $GLOBAL_STYLE -> 事实源（活链，globalCss 单份）"
  else
    echo "error: $GLOBAL_STYLE 软链未指向事实源（$(readlink "$GLOBAL_STYLE" || echo '?')）——" >&2
    echo "       若已 dangling，MPE 下次读失败会写穿覆盖事实源；" >&2
    echo "       修复：ln -sfn '$SRC/style.less' '$GLOBAL_STYLE'" >&2
    exit 1
  fi
elif [[ -e $GLOBAL_STYLE ]]; then
  echo "warn: $GLOBAL_STYLE 是实体文件（可能是 MPE 回写的 stub 或旧定制）——" >&2
  echo "      全局层与事实源分叉，globalCss 走 concat 双份；" >&2
  echo "      要统一就备份后 ln -sfn '$SRC/style.less' '$GLOBAL_STYLE'" >&2
else
  echo "warn: $GLOBAL_STYLE 不存在——全局层未启用，MPE 会自写默认 stub；" >&2
  echo "      要启用全局样式：mkdir -p '${GLOBAL_STYLE%/*}' && ln -s '$SRC/style.less' '$GLOBAL_STYLE'" >&2
fi
