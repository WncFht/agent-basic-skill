---
name: paperflow-pipeline-notes
description: Use when the user wants to create or update a Chinese deep paper note by driving the external paperflow repository and a local research-notes workspace.
---

# Paperflow Pipeline Notes Wrapper

这是一个 thin wrapper。真正的运行时代码位于外部 `WncFht/paperflow` 仓库中；笔记目标工作区位于独立的 `research-notes` 目录中。

## 先解析外部路径

优先级：

1. 显式参数：`--paperflow-repo`、`--research-notes-root`
2. 环境变量：`PAPERFLOW_REPO`、`RESEARCH_NOTES_ROOT`
3. 本地 source override：`repo:WncFht/paperflow`、`workspace:research-notes`
4. 默认候选路径：`$HOME/Desktop/src/paperflow`、`$HOME/Desktop/src/research-notes`

解析示例：

```bash
python scripts/resolve_paperflow_paths.py --json
```

## 推荐命令

```bash
PAPERFLOW_REPO="$(python scripts/resolve_paperflow_paths.py --print paperflow_repo)"
RESEARCH_NOTES_ROOT="$(python scripts/resolve_paperflow_paths.py --print research_notes_root)"

uv run --project "$PAPERFLOW_REPO" paperflow add "https://arxiv.org/abs/<paper_id>"
```

如果只知道标题：

```bash
PAPERFLOW_REPO="$(python scripts/resolve_paperflow_paths.py --print paperflow_repo)"

python "$PAPERFLOW_REPO/scripts/paperflow_prepare_from_title.py" "<paper_title>"
```

## 约定

- `paperflow` 负责下载、解析和辅助脚本
- `research-notes` 负责承载 `paper.ipynb`
- 不要把 PDF、notebook、缓存或运行时中间产物写回 skill 目录
- 如果 `research-notes` 路径不存在，应先设置 `RESEARCH_NOTES_ROOT` 或在 local source override 中登记
