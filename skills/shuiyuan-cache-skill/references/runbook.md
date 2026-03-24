# Shuiyuan 运行手册

状态：当前有效运行手册（skill-first / cache-first）

## 当前推荐工作流

推荐顺序：

```text
auth -> ensure_cached -> query/summary -> export
```

含义：

1. 先建立长期可复用登录态；
2. 再把 topic 同步到本地缓存；
3. 查询和摘要尽量只读本地缓存；
4. 只有需要给人阅读 Markdown 时再导出。

## 默认运行时目录

当前默认不会把运行时数据写在 repo 根目录，而是写到：

```text
~/.local/share/shuiyuan-cache-skill/
```

主要结构：

```text
~/.local/share/shuiyuan-cache-skill/
  cache/
  exports/
  cookies.txt
```

认证相关：

```text
cache/auth/auth.json
cache/auth/browser_profile/
```

详细结构见 `references/runtime_layout.md`。

## 初始化

```bash
REPO_ROOT="${SHUIYUAN_EXPORTER_REPO:-$HOME/Desktop/src/shuiyuan_exporter}"
cd "$REPO_ROOT"
uv python install 3.12
uv sync --group dev
```

## 建立认证

推荐方式：独立浏览器 profile + `auth.json`。

```bash
uv run python -m shuiyuan_cache.cli.auth_cli setup
```

查看认证状态：

```bash
uv run python -m shuiyuan_cache.cli.auth_cli status
```

如果只想复用现有 profile 重新导出登录态：

```bash
uv run python -m shuiyuan_cache.cli.auth_cli refresh
```

## 缓存一个 topic

推荐使用机器安全的脚本入口：

```bash
uv run python scripts/ensure_cached.py 456491
uv run python scripts/ensure_cached.py https://shuiyuan.sjtu.edu.cn/t/topic/456491 --refresh-mode incremental
uv run python scripts/ensure_cached.py 456491 --refresh-mode full --no-images
```

## 在线搜索与作者追踪

快速候选搜索：

```bash
uv run python scripts/search_forum.py 炒股 --mode header
```

完整 Discourse 搜索：

```bash
uv run python scripts/search_forum.py '搜索 user:pangbo order:latest' --mode full-page
```

作者追踪：

```bash
uv run python scripts/trace_author.py pangbo
uv run python scripts/trace_author.py pangbo --keyword 搜索 --cache-topics 3
```

## 查询和摘要

查询：

```bash
uv run python scripts/query_topic.py 456491 --keyword 安全 --limit 5
uv run python scripts/query_topic.py 456491 --author FleetSnowfluff
```

摘要：

```bash
uv run python scripts/summarize_topic.py 456491 --focus-keyword Openclaw
uv run python scripts/summarize_topic.py 456491 --recent-days 7
```

## 导出 Markdown

```bash
uv run python scripts/export_topic.py 456491
```

默认输出：

```text
~/.local/share/shuiyuan-cache-skill/exports/<topic_id>/
```

## 机器输出约定

`scripts/*.py` 约定：

- `stdout`：只输出 JSON
- `stderr`：输出进度和阶段日志

## 兼容入口

下面入口仍保留，但属于 legacy：

```bash
uv run python -m shuiyuan_cache.cli.export_cli
uv run python main.py
```
