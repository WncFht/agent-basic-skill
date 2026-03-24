# Install agent-basic-skill

这个仓库里的每个 `skills/<skill-name>/` 目录都是独立安装单元。安装或更新时，优先使用顶层安装器，它会在复制 skill 目录前先处理 wrapper 所需的外部依赖仓。

## 推荐方式

安装单个 skill：

```bash
python scripts/install_skill.py jupyter-notebook
```

安装带外部工具仓的 wrapper：

```bash
python scripts/install_skill.py bilibili-up-digest shuiyuan-cache-skill
```

安装器的行为：

- 先读取 `skills/<skill-name>/external-repos.json`
- 按 `env var -> local override -> default_detect_paths -> default_clone_dir` 检查外部仓
- 已存在合法仓时跳过 clone
- 仓缺失时自动 clone 到 `default_clone_dir`
- `~/.codex/skills/<skill-name>/` 已存在时，视为受管安装副本并整体替换

## 仍可手动覆盖安装

如果你明确知道外部仓已经准备好，也可以继续手动覆盖：

```bash
mkdir -p "$HOME/.codex/skills/jupyter-notebook"
rsync -a --delete skills/jupyter-notebook/ "$HOME/.codex/skills/jupyter-notebook/"
```

刷新全部 skills：

```bash
mkdir -p "$HOME/.codex/skills"
rsync -a --delete skills/ "$HOME/.codex/skills/"
```

`rsync -a --delete` 的含义是：

- 保留目录结构与文件权限
- 覆盖已存在文件
- 删除目标目录里已经不再存在于仓库中的旧文件

## Wrapper skill 的外部仓准备

`bilinote-video-note`、`paperflow-pipeline-notes`、`shuiyuan-cache-skill`、`bilibili-up-digest` 这几个 skill 只包含入口文档和桥接脚本；真正的工具仓仍应单独放在本机，例如 `~/Desktop/src/...`。

推荐把本机 source override 放在：

```bash
mkdir -p "$HOME/.codex/state/agent-basic-skill"
cp local/source-overrides.example.json \
  "$HOME/.codex/state/agent-basic-skill/source-overrides.json"
```

然后根据实际 clone 路径修改，并导出：

```bash
export AGENT_BASIC_SKILL_SOURCE_OVERRIDES="$HOME/.codex/state/agent-basic-skill/source-overrides.json"
```

如果你就是在这个仓库里维护 skills，也可以改用被 `.gitignore` 忽略的 `local/source-overrides.json`。

## 为什么不要只复制 `SKILL.md`

这个仓库里的部分 skill 不是单文件：

- `jupyter-notebook` 依赖模板、参考文档和脚手架脚本
- `report-download` 依赖 Python 脚本和 `pyproject.toml`
- `frontend-slides` 依赖 companion markdown、CSS 和脚本
- 几个 wrapper skill 依赖路径解析脚本、参考文档和 `external-repos.json`

所以安装时应始终复制整个 `skills/<skill-name>/` 目录。

## GitHub 安装方式

如果这个仓库发布到 GitHub，推荐继续按“整个 skill 目录”安装，而不是只取一个原始文件。

先设置 `CODEX_HOME`：

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
```

安装单个 skill：

```bash
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo <owner>/agent-basic-skill \
  --path skills/jupyter-notebook
```

安装多个 skill 时，把多个 `--path skills/<skill-name>` 依次传入即可。
