# agent-basic-skill

`agent-basic-skill` 是一个可复用的 Codex skills 仓库。每个 skill 都直接存放在 `skills/<skill-name>/` 下，整个目录就是安装、同步和覆盖更新的最小单位。

这个仓库不再维护额外的仓库级安装元数据。以后安装时，直接把目标 skill 目录整体覆盖到 `~/.codex/skills/<skill-name>/` 即可。

## 使用方法

安装单个 skill：

```bash
mkdir -p "$HOME/.codex/skills/jupyter-notebook"
rsync -a --delete skills/jupyter-notebook/ "$HOME/.codex/skills/jupyter-notebook/"
```

刷新整个 skills 仓：

```bash
mkdir -p "$HOME/.codex/skills"
rsync -a --delete skills/ "$HOME/.codex/skills/"
```

如果未来从 GitHub 安装，请始终安装整个 `skills/<skill-name>/` 目录，而不是只拷贝一个 `SKILL.md`，因为有些 skill 还依赖相邻脚本、模板、资源或参考文档。

更多示例见 [INSTALL.md](INSTALL.md)。

## 技能列表

### [pdf](skills/pdf/SKILL.md)

PDF 解析、生成与版式校验。

### [report-download](skills/report-download/SKILL.md)

官方来源优先的 A 股和港股财报下载。

### [git-commit](skills/git-commit/SKILL.md)

Conventional Commits 工作流。

### [jupyter-notebook](skills/jupyter-notebook/SKILL.md)

Notebook 创建、模板化与脚手架生成。

### [frontend-slides](skills/frontend-slides/SKILL.md)

HTML 幻灯片与 PPT 转网页。

### [bilinote-video-note](skills/bilinote-video-note/SKILL.md)

调用外部 `WncFht/BiliNote` 仓生成视频笔记。

### [paperflow-pipeline-notes](skills/paperflow-pipeline-notes/SKILL.md)

调用外部 `WncFht/paperflow` 仓并配合本地 notes 工作区。

### [shuiyuan-cache-skill](skills/shuiyuan-cache-skill/SKILL.md)

调用外部 `WncFht/shuiyuan_exporter` 仓并使用外部 runtime cache。

### [bilibili-up-digest](skills/bilibili-up-digest/SKILL.md)

调用外部 `WncFht/PulseDeck` 仓写入本地 Obsidian bilibili vault。

## Thin Wrapper 说明

仓库里的 wrapper skill 只保留入口文档和少量桥接脚本，真正的运行时代码仍在外部工具仓里。约束见 [docs/thin-wrapper-skills.md](docs/thin-wrapper-skills.md)。

## 本地 source override

wrapper skill 的外部仓路径支持本地 override。推荐做法：

1. 把实际 override 文件放在 `~/.codex/state/agent-basic-skill/source-overrides.json`
2. 或在本仓中使用一个被 `.gitignore` 忽略的 `local/source-overrides.json`
3. 通过 `AGENT_BASIC_SKILL_SOURCE_OVERRIDES` 指向实际要使用的文件

格式示例见 [local/source-overrides.example.json](local/source-overrides.example.json)。

## 目录结构

```text
agent-basic-skill/
├── INSTALL.md
├── README.md
├── docs/
│   └── thin-wrapper-skills.md
├── local/
│   └── source-overrides.example.json
├── skills/
│   ├── pdf/
│   ├── report-download/
│   ├── git-commit/
│   ├── jupyter-notebook/
│   ├── frontend-slides/
│   ├── bilinote-video-note/
│   ├── paperflow-pipeline-notes/
│   ├── shuiyuan-cache-skill/
│   └── bilibili-up-digest/
└── tests/
```

## 验证

运行下面的命令可以验证仓库结构和 wrapper 路径解析逻辑：

```bash
python -m unittest discover -s tests
```
