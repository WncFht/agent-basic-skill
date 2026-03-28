# agent-basic-skill

`agent-basic-skill` 是一个可复用的 Codex skills 仓库。每个 skill 都直接存放在 `skills/<skill-name>/` 下，整个目录就是安装、同步和覆盖更新的最小单位。

如果你要让外部 AGENT 通过一句固定指令完成安装，使用面向 agent 的入口文档：[`.codex/INSTALL.md`](.codex/INSTALL.md)。

对于 `bundle-native` skill，安装时只需要复制 skill 目录本身。对于 `external-tool-wrapper` skill，仓库还会附带一个机器可读的 `external-repos.json`，用于在显式安装时确保外部依赖仓已经存在；如果默认位置已经有合法仓库，则会直接跳过 clone。

## 使用方法

安装单个 skill：

```bash
mkdir -p "$HOME/.codex/skills/deepresearch-skill"
rsync -a --delete skills/deepresearch-skill/ "$HOME/.codex/skills/deepresearch-skill/"
```

或使用统一安装器：

```bash
python scripts/install_skill.py deepresearch-skill
```

安装带外部依赖仓的 wrapper：

```bash
python scripts/install_skill.py bilibili-up-digest shuiyuan-cache-skill video-note-render-pdf-v0 video-note-render-pdf-v1 video-note-render-pdf-v2
```

这个命令会先检查 wrapper 声明的外部仓：

- 已存在且满足 marker 时：跳过 clone
- 不存在时：自动 clone 到文档化默认目录
- 默认 clone 目录已存在但不是合法仓时：明确报错，不覆盖脏目录

刷新整个 skills 仓：

```bash
mkdir -p "$HOME/.codex/skills"
rsync -a --delete skills/ "$HOME/.codex/skills/"
```

如果未来从 GitHub 安装，请始终安装整个 `skills/<skill-name>/` 目录，而不是只拷贝一个 `SKILL.md`，因为有些 skill 还依赖相邻脚本、模板、资源或参考文档。对于 external wrapper，还需要同时准备它声明的外部源仓。

更多示例见 [INSTALL.md](INSTALL.md)。

## 技能列表

### [pdf](skills/pdf/SKILL.md)

PDF 解析、生成与版式校验。

### [report-download](skills/report-download/SKILL.md)

官方来源优先的 A 股和港股财报下载。

### [git-commit](skills/git-commit/SKILL.md)

Conventional Commits 工作流。

### [jujutsu](skills/jujutsu/SKILL.md)

Jujutsu (`jj`) 版本控制工作流与 agent 安全操作约束。

### [jupyter-notebook](skills/jupyter-notebook/SKILL.md)

Notebook 创建、模板化与脚手架生成。

### [deepresearch-skill](skills/deepresearch-skill/SKILL.md)

多模态证据驱动的深度研究报告与 LaTeX/PDF 交付。

### [public-ai-resource-research](skills/public-ai-resource-research/SKILL.md)

公开 AI 资源站点、导航页、relay、中转站、模型与状态线索的结构化调研与 ledger 产出。

### [relay-endpoint-probe](skills/relay-endpoint-probe/SKILL.md)

探测 LLM 中转接口、识别 OpenAI/Codex/Anthropic 兼容性，并衔接本机 CCH/check-cx 接入。

### [codex-cli-orchestrator](skills/codex-cli-orchestrator/SKILL.md)

把 `codex exec` 当成可批量编排的 worker，落盘事件、状态与结果。

### [frontend-slides](skills/frontend-slides/SKILL.md)

HTML 幻灯片与 PPT 转网页。

### [tauri-devtools](skills/tauri-devtools/SKILL.md)

Tauri 应用调试、截图、DOM 检查、IPC 监控与窗口管理。

### [web-devtools](skills/web-devtools/SKILL.md)

基于 browser-use CLI 的浏览器自动化、截图、交互与云端浏览器调试。

### [bilinote-video-note](skills/bilinote-video-note/SKILL.md)

调用外部 `WncFht/BiliNote` 仓生成视频笔记。

### [paperflow-pipeline-notes](skills/paperflow-pipeline-notes/SKILL.md)

调用外部 `WncFht/paperflow` 仓并配合本地 notes 工作区。

### [shuiyuan-cache-skill](skills/shuiyuan-cache-skill/SKILL.md)

调用外部 `WncFht/shuiyuan_exporter` 仓并使用外部 runtime cache。

### [bilibili-up-digest](skills/bilibili-up-digest/SKILL.md)

调用外部 `WncFht/PulseDeck` 仓写入本地 Obsidian bilibili vault。

### [video-note-render-pdf-v0](skills/video-note-render-pdf-v0/SKILL.md)

修改前基线版的视频讲义 wrapper，便于和后续版本并行使用与对比。

### [video-note-render-pdf-v1](skills/video-note-render-pdf-v1/SKILL.md)

统一 YouTube / Bilibili 视频讲义 wrapper，解析外部 runtime repo 与本地 case workspace。

### [video-note-render-pdf-v2](skills/video-note-render-pdf-v2/SKILL.md)

在 v1 基础上增加字幕字数 guardrail、三轴路由、视觉义务 ledger 与 revision action contract 的新版 wrapper。

## Thin Wrapper 说明

仓库里的 wrapper skill 只保留入口文档和少量桥接脚本，真正的运行时代码仍在外部工具仓里。约束见 [docs/thin-wrapper-skills.md](docs/thin-wrapper-skills.md)。

依赖仓声明格式与安装边界见 [docs/external-repo-manifests.md](docs/external-repo-manifests.md)。

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
│   ├── external-repo-manifests.md
│   └── thin-wrapper-skills.md
├── local/
│   └── source-overrides.example.json
├── scripts/
│   └── install_skill.py
├── skills/
│   ├── pdf/
│   ├── report-download/
│   ├── git-commit/
│   ├── jujutsu/
│   ├── jupyter-notebook/
│   ├── deepresearch-skill/
│   ├── public-ai-resource-research/
│   ├── relay-endpoint-probe/
│   ├── codex-cli-orchestrator/
│   ├── frontend-slides/
│   ├── tauri-devtools/
│   ├── web-devtools/
│   ├── bilinote-video-note/
│   ├── paperflow-pipeline-notes/
│   ├── shuiyuan-cache-skill/
│   ├── bilibili-up-digest/
│   ├── video-note-render-pdf-v0/
│   ├── video-note-render-pdf-v1/
│   └── video-note-render-pdf-v2/
└── tests/
```

## 迁移说明

旧的 `~/.codex/skills/video-note-skill` 已转为迁移来源，不再作为长期主源维护。当前统一入口保留 `video-note-render-pdf-v0` 基线版、`video-note-render-pdf-v1` 改进版与 `video-note-render-pdf-v2` 结构化增强版；平台差异应继续下沉到外部 runtime repo 的 adapter 层，而不是在 bundle 仓里维护两套平行 skill。

## 验证

运行下面的命令可以验证仓库结构、安装器和 wrapper 路径解析逻辑：

```bash
python -m unittest discover -s tests
```
