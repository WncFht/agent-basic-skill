---
name: bilibili-up-digest
description: Use when the user wants to maintain daily Bilibili creator digests through the external PulseDeck repository and a local Obsidian bilibili vault.
---

# Bilibili UP Digest Wrapper

这是一个 thin wrapper。真正的代码与运行逻辑位于外部 `WncFht/PulseDeck` 仓库中；Obsidian vault、配置文件和 runtime 产物都位于当前 skill 目录之外。

## 先解析外部仓路径

优先级：

1. 显式参数：`--repo-root`
2. 环境变量：`BILIBILI_UP_DIGEST_REPO`
3. 本地 source override：`repo:WncFht/PulseDeck`
4. 默认候选路径：`$HOME/Desktop/src/PulseDeck`、`$HOME/Desktop/src/pulsedeck`

解析示例：

```bash
python scripts/resolve_pulsedeck_repo.py --json
```

## Runtime 路径

- `BILIBILI_DIGEST_VAULT_ROOT` 默认回退到 `$HOME/Desktop/obsidian/bilibili`
- `BILIBILI_DIGEST_CONFIG` 默认回退到 `$BILIBILI_DIGEST_VAULT_ROOT/配置/关注UP.yaml`
- Digest 运行产物应继续放在 vault 自己的 runtime 目录或工具仓定义的位置，不应回写到当前 skill 目录

## 推荐命令

```bash
REPO_ROOT="$(python scripts/resolve_pulsedeck_repo.py --print repo_root)"
VAULT_ROOT="${BILIBILI_DIGEST_VAULT_ROOT:-$HOME/Desktop/obsidian/bilibili}"
CONFIG_PATH="${BILIBILI_DIGEST_CONFIG:-$VAULT_ROOT/配置/关注UP.yaml}"

uv run --project "$REPO_ROOT" python scripts/build_daily_digest.py \
  --vault-root "$VAULT_ROOT" \
  --config "$CONFIG_PATH"
```

## 约定

- 每个视频仍然只保留一份 canonical note
- 日报、UP 主索引页和主题索引页都属于 vault 内容，而不是 wrapper skill 内容
- 如果 PulseDeck 仓不存在，应先 clone 到 `Desktop/src` 或设置 `BILIBILI_UP_DIGEST_REPO`
