# Install agent-basic-skill

这个仓库里的每个 `skills/<skill-name>/` 目录都是独立安装单元。安装或更新时，优先使用顶层安装器。

## 推荐方式

```bash
python scripts/install_skill.py asr --dest-root ~/.agents/skills
python scripts/install_skill.py asr figure-viz link-get paper-search video-render-pdf setup-toolchain skill-management document-writing conventional-commits --dest-root ~/.agents/skills
```

安装器的行为：

- 把指定的目的目录视为受管安装副本并整体替换为当前仓库版本；安装前保存本地修改
- 以 JSON 输出每个 skill 的安装结果（`--json` 可用于脚本集成）

安装器保留原有默认目的目录 `$CODEX_HOME/skills`（通常是 `~/.codex/skills`）。新增 skill 的依赖声明和跨 skill 调用使用 `~/.agents/skills/<name>/`，因此显式传入 `--dest-root ~/.agents/skills`。共享目录已有同名版本时按需更新，避免在私有目录重复安装。

安装不下载模型或创建虚拟环境。按各 skill 的 `SKILL.md` 与 `deps.toml` 初始化外部依赖。停止使用的 skill 在 `vendor/` 中归档，安装器不再按这些名称安装，完整列表见 [vendor/README.md](vendor/README.md)。

手动方式也完全可以——复制整个目录即可：

```bash
mkdir -p "$HOME/.agents/skills/<skill-name>"
rsync -a --delete skills/<skill-name>/ "$HOME/.agents/skills/<skill-name>/"
```

## 同步 local agents

```bash
mkdir -p "$HOME/.codex/agents"
rsync -a agents/ "$HOME/.codex/agents/"
```

## 按需安装的 skill

`peer-sessions` 保存在 `skills/`，不包含在上述默认安装命令中。`memory-skill`、`paper-note-skill`、`frontend-design` 和 `diagram-design` 已停止使用，保存在 `vendor/`，不参与安装。归档不会自动删除已安装的副本。
