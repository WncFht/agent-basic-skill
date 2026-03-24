# Troubleshooting

## Auth expired or missing

First check whether the saved login state still works against the live forum:

```bash
uv run python -m shuiyuan_cache.cli.auth_cli status \
  --cache-root "$HOME/.local/share/shuiyuan-cache-skill/cache" \
  --cookie-path "$HOME/.local/share/shuiyuan-cache-skill/cookies.txt" \
  --check-live --json
```

Notes:

- `cookies.txt` stores an HTTP `Cookie` header string, not a curl cookie-jar file
- `auth_cli setup` opens a dedicated browser profile and waits for Enter after you finish login in the browser window

Rebuild auth state with the same runtime paths used by the skill scripts:

```bash
uv run python -m shuiyuan_cache.cli.auth_cli setup \
  --cache-root "$HOME/.local/share/shuiyuan-cache-skill/cache" \
  --cookie-path "$HOME/.local/share/shuiyuan-cache-skill/cookies.txt"
```

## Topic not cached

Run:

```bash
uv run python scripts/ensure_cached.py <topic>
```

## Need a stronger refresh

Use one of:

- `--refresh-mode incremental`
- `--refresh-mode refresh-tail`
- `--refresh-mode full`

## Export produced incomplete media links

Run `ensure_cached.py` first so the raw/json/image cache is available, then rerun `export_topic.py`.
