#!/usr/bin/env bash
# install_bbdown.sh — 安装/升级 BBDown，幂等。
# nilaoda/BBDown 已归档：默认分支被换成 DELETED 占位（AUR bbdown-git 因此构建失败），
# 必须从 master 分支源码 dotnet publish。有源码树则 git fetch + reset 到 master HEAD。
set -euo pipefail

SRC="${BBDOWN_SRC:-$HOME/.cache/bbdown-build/BBDown}"
BIN="${BBDOWN_BIN:-$HOME/.local/bin}"

case "$(uname -sm)" in
"Linux x86_64") RID=linux-x64 ;;
"Darwin arm64") RID=osx-arm64 ;;
"Darwin x86_64") RID=osx-x64 ;;
*)
  echo "未知平台 $(uname -sm)，请手动指定 RID" >&2
  exit 1
  ;;
esac

command -v dotnet >/dev/null 2>&1 || {
  echo "缺 dotnet-sdk：Arch 装 sudo pacman -S dotnet-sdk，macOS 装 brew install dotnet-sdk" >&2
  exit 1
}

if [ -d "$SRC/.git" ]; then
  git -C "$SRC" fetch --depth 50 origin master
  if [ "$(git -C "$SRC" rev-parse HEAD)" = "$(git -C "$SRC" rev-parse FETCH_HEAD)" ] && [ -x "$BIN/BBDown" ]; then
    echo "BBDown 已是最新（$(git -C "$SRC" rev-parse --short HEAD)），跳过构建"
    exit 0
  fi
  git -C "$SRC" reset --hard FETCH_HEAD
else
  git clone -b master --depth 50 https://github.com/nilaoda/BBDown.git "$SRC"
fi

cd "$SRC"
dotnet publish BBDown -r "$RID" -c Release -o artifact
mkdir -p "$BIN"
cp artifact/BBDown "$BIN/BBDown"
chmod +x "$BIN/BBDown"
echo "BBDown $(git rev-parse --short HEAD) -> $BIN/BBDown"
