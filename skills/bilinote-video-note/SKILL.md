---
name: bilinote-video-note
description: Use when the user wants to turn one or more Bilibili video URLs into Markdown notes with the external BiliNote repository, without starting the frontend/backend web services.
---

# BiliNote 视频笔记 Wrapper

这是一个 thin wrapper。真正的运行时代码位于外部 `WncFht/BiliNote` 仓库中；本 skill 只保留调用说明和轻量路径解析脚本。

## 先解析外部仓路径

优先级：

1. 显式参数：`--backend-root` / `--repo-root`
2. 环境变量：`BILINOTE_BACKEND_ROOT`、`BILINOTE_REPO`
3. 本地 source override：`repo:WncFht/BiliNote`
4. 默认候选路径：`$HOME/Desktop/src/BiliNote/backend`、`$HOME/Desktop/src/BiliNote`

解析示例：

```bash
python scripts/resolve_bilinote_paths.py --json
```

只打印 backend 根目录：

```bash
python scripts/resolve_bilinote_paths.py --print backend_root
```

## 默认输出参数

- Markdown 输出目录默认使用 `BILINOTE_OUTPUT_DIR`，若未设置则回退到 `$HOME/Desktop/obsidian/视频`
- 默认 style 是 `detailed`
- 默认关闭截图

## 推荐命令

```bash
BACKEND_ROOT="$(python scripts/resolve_bilinote_paths.py --print backend_root)"
OUTPUT_DIR="${BILINOTE_OUTPUT_DIR:-$HOME/Desktop/obsidian/视频}"

uv run --project "$BACKEND_ROOT" bilinote-cli "<BILIBILI_URL>" --output "$OUTPUT_DIR"
```

批量处理：

```bash
BACKEND_ROOT="$(python scripts/resolve_bilinote_paths.py --print backend_root)"
OUTPUT_DIR="${BILINOTE_OUTPUT_DIR:-$HOME/Desktop/obsidian/视频}"

uv run --project "$BACKEND_ROOT" bilinote-cli \
  "<BILIBILI_URL_1>" "<BILIBILI_URL_2>" \
  --jobs 2 \
  --output "$OUTPUT_DIR"
```

## 约定

- 不要在 skill 目录里放置 BiliNote 的后端源码、模型缓存或数据库
- 继续复用外部仓中的 `.env`、SQLite provider、模型配置和本地转录能力
- 如果路径解析失败，应先准备外部 `BiliNote` 仓，或设置 `BILINOTE_REPO` / `BILINOTE_BACKEND_ROOT`
