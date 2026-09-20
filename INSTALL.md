# Install agent-basic-skill

这个仓库里的每个 `skills/<skill-name>/` 目录都是独立安装单元。安装或更新时，优先使用顶层安装器。

## 推荐方式

```bash
python scripts/install_skill.py memory-skill
python scripts/install_skill.py paper-note-skill plot-skill report-download
```

安装器的行为：

- 把 `~/.codex/skills/<skill-name>/` 视为受管安装副本并整体替换为当前仓库版本
- 以 JSON 输出每个 skill 的安装结果（`--json` 可用于脚本集成）

手动方式也完全可以——复制整个目录即可：

```bash
mkdir -p "$HOME/.codex/skills/<skill-name>"
rsync -a --delete skills/<skill-name>/ "$HOME/.codex/skills/<skill-name>/"
```

## 同步 local agents

```bash
mkdir -p "$HOME/.codex/agents"
rsync -a agents/ "$HOME/.codex/agents/"
```

## memory-skill 首次使用

memory-skill 安装后还需要初始化或接管一个 memory 数据仓：

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh --memory-root ~/.codex/memory
```

详见 [skills/memory-skill/README.md](skills/memory-skill/README.md)。
