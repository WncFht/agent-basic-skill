---
name: shuiyuan-cache-skill
description: Use when the user needs cache-first or live-search access to Shuiyuan topics through the external shuiyuan_exporter repository.
---

# Shuiyuan Cache Wrapper

这是一个 thin wrapper。真正的运行时代码位于外部 `WncFht/shuiyuan_exporter` 仓库中；cache、auth 和导出目录都位于当前 skill 目录之外。

## 先解析外部仓路径

优先级：

1. 显式参数：`--repo-root`
2. 环境变量：`SHUIYUAN_EXPORTER_REPO`
3. 本地 source override：`repo:WncFht/shuiyuan_exporter`
4. 默认候选路径：`$HOME/Desktop/src/shuiyuan_exporter`

解析示例：

```bash
python scripts/resolve_shuiyuan_paths.py --json
```

## Runtime 路径

- `SHUIYUAN_CACHE_ROOT` 默认回退到 `~/.local/share/shuiyuan-cache-skill`
- 认证状态、cookie、SQLite 数据库、媒体缓存都必须继续留在当前 skill 目录之外

## 推荐命令

```bash
REPO_ROOT="$(python scripts/resolve_shuiyuan_paths.py --print repo_root)"
CACHE_ROOT="${SHUIYUAN_CACHE_ROOT:-$HOME/.local/share/shuiyuan-cache-skill}"

uv run --project "$REPO_ROOT" python -m shuiyuan_cache.cli.auth_cli status \
  --cache-root "$CACHE_ROOT/cache" \
  --cookie-path "$CACHE_ROOT/cookies.txt" \
  --check-live
```

## 约定

- 不要把 `cache/`、`auth.json`、`browser_profile/` 或导出结果塞进 skill 目录
- 若缺少外部仓，请先 clone `WncFht/shuiyuan_exporter`，或设置 `SHUIYUAN_EXPORTER_REPO`
