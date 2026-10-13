#!/usr/bin/env bash
# 编译笔记 tex 并做最低限度验证。
# 用法: scripts/compile.sh notes.tex   （在 tex 所在目录外调用亦可）
set -u
TEX="${1:?usage: compile.sh <file.tex>}"
DIR=$(dirname "$TEX")
BASE=$(basename "$TEX" .tex)
cd "$DIR" || exit 1

if command -v latexmk >/dev/null 2>&1; then
  # latexmk 自动决定重跑次数（TOC/交叉引用收敛为止）
  latexmk -xelatex -interaction=nonstopmode -halt-on-error "$BASE.tex" >compile.log 2>&1
  rc=$?
  [ $rc -ne 0 ] && {
    echo "latexmk FAILED (rc=$rc)"
    grep -n "^!" compile.log | head -20
    exit 1
  }
  echo "latexmk ok"
else
  for i in 1 2; do
    xelatex -interaction=nonstopmode -halt-on-error "$BASE.tex" >"compile_pass$i.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ] || grep -q "^!" "compile_pass$i.log"; then
      echo "PASS $i FAILED (rc=$rc)"
      grep -n "^!" "compile_pass$i.log" | head -20
      grep -qi "fandol\|fontspec.*not found" "compile_pass$i.log" &&
        echo "提示: 像是字体缺失 —— 按平台换 ctex fontset(fandol/mac/windows)"
      exit 1
    fi
    echo "pass $i ok"
  done
fi

PAGES=$(pdfinfo "$BASE.pdf" 2>/dev/null | awk '/^Pages/{print $2}')
SIZE=$(stat -c%s "$BASE.pdf" 2>/dev/null || stat -f%z "$BASE.pdf")
echo "OK: $BASE.pdf  pages=${PAGES:-?}  size=${SIZE}B"

# 渲染首页供快速目检；pdftoppm 按总页数零填充（10+ 页时是 _p1-01.png），
# 取实际产物文件名而不是写死
pdftoppm -png -r 60 -f 1 -l 1 "$BASE.pdf" "${BASE}_p1" 2>/dev/null &&
  echo "preview -> $(ls "${BASE}"_p1-*.png 2>/dev/null | head -1)"
# 多页目检：pdftoppm -f N -l N -r 55 -png "$BASE.pdf" pg（sips 只渲染第 1 页）
rm -f compile_pass*.log
