# Install agent-basic-skill

这个仓库里的每个 `skills/<skill-name>/` 目录都是独立安装单元。安装或更新时，直接覆盖目标目录即可。

## 本地仓库工作流

安装单个 skill：

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

如果你只想看有哪些 skills，可直接查看 `skills/` 目录。

## 更新已有安装

拉取仓库最新变更后，重复同样的覆盖命令即可：

```bash
git pull
rsync -a --delete skills/ "$HOME/.codex/skills/"
```

如果只刷新单个 skill：

```bash
git pull
rsync -a --delete skills/pdf/ "$HOME/.codex/skills/pdf/"
```

## 为什么不要只复制 `SKILL.md`

这个仓库里的部分 skill 不是单文件：

- `jupyter-notebook` 依赖模板、参考文档和脚手架脚本
- `report-download` 依赖 Python 脚本和 `pyproject.toml`
- `frontend-slides` 依赖 companion markdown、CSS 和脚本
- 几个 wrapper skill 依赖路径解析脚本

所以安装时应始终复制整个 `skills/<skill-name>/` 目录。

## Wrapper skill 的额外准备

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
