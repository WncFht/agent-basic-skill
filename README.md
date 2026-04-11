# agent-basic-skill

`agent-basic-skill` 是一个可复用的 Codex skills 与 local agents 仓库。每个 skill 都直接存放在 `skills/<skill-name>/` 下，整个目录就是安装、同步和覆盖更新的最小单位；可复用的本地 agent 配置则放在 `agents/*.toml`。

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

同步本仓附带的 local agents：

```bash
mkdir -p "$HOME/.codex/agents"
rsync -a agents/ "$HOME/.codex/agents/"
```

如果未来从 GitHub 安装，请始终安装整个 `skills/<skill-name>/` 目录，而不是只拷贝一个 `SKILL.md`，因为有些 skill 还依赖相邻脚本、模板、资源或参考文档。对于 external wrapper，还需要同时准备它声明的外部源仓。

更多示例见 [INSTALL.md](INSTALL.md)。

## 技能列表

### [BetterGPT](skills/BetterGPT/SKILL.md)

工作区主入口 skill。默认先路由到 `BetterLanguage`，再按任务命中叠加 `BetterFrontend`、`BetterVibe`、`BetterTrellis` 与 `BetterSubagents`。

### [pdf](skills/pdf/SKILL.md)

PDF 解析、生成与版式校验。

### [report-download](skills/report-download/SKILL.md)

官方来源优先的 A 股和港股财报下载。

### [git-commit](skills/git-commit/SKILL.md)

Conventional Commits 工作流。

### [jujutsu](skills/jujutsu/SKILL.md)

Jujutsu (`jj`) 版本控制工作流、JJ-first agent 安全约束与按需参考文档。

### [jupyter-notebook](skills/jupyter-notebook/SKILL.md)

Notebook 创建、模板化与脚手架生成。

### [deepresearch-skill](skills/deepresearch-skill/SKILL.md)

多模态证据驱动的深度研究报告与 LaTeX/PDF 交付。
介绍、截图和仓库内示例见 [skills/deepresearch-skill/README.md](skills/deepresearch-skill/README.md)。

### [public-ai-resource-research](skills/public-ai-resource-research/SKILL.md)

公开 AI 资源站点、导航页、relay、中转站、模型与状态线索的结构化调研与 ledger 产出。

### [relay-endpoint-probe](skills/relay-endpoint-probe/SKILL.md)

探测 LLM 中转接口、识别 OpenAI/Codex/Anthropic 兼容性，并衔接本机 CCH/check-cx 接入。

### [codex-cli-orchestrator](skills/codex-cli-orchestrator/SKILL.md)

把 `codex exec` 当成可批量编排的 worker，落盘事件、状态与结果。

### [frontend-slides](skills/frontend-slides/SKILL.md)

HTML 幻灯片与 PPT 转网页。

### [frontend-style-mimic](skills/frontend-style-mimic/SKILL.md)

从现有前端代码库提取可复用风格包，并支持按风格实现、评审和派生变体。

### [slidev](skills/slidev/SKILL.md)

端到端 Slidev 演示文稿 workflow，覆盖调研、结构规划、演讲稿、SVG 资产和 HTML/PDF/PPTX 导出。
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

## Local Agents

仓库同时附带一组可复用的本地 agent 配置，位于 `agents/`：

- `code-mapper`
- `docs-researcher`
- `browser-debugger`
- `reviewer`
- `search-specialist`
- `frontend-developer`
- `refactoring-specialist`
- `worker`
- `explorer`
- `shell-script-expert`

它们不是 native skill bundle 的一部分；如果要在当前机器的 Codex 中启用，需额外同步到 `~/.codex/agents/`。

## Thin Wrapper 说明

仓库里的 wrapper skill 只保留入口文档和少量桥接脚本，真正的运行时代码仍在外部工具仓里。约束见 [docs/thin-wrapper-skills.md](docs/thin-wrapper-skills.md)。

依赖仓声明格式与安装边界见 [docs/external-repo-manifests.md](docs/external-repo-manifests.md)。

## 参考

- [LSTM-Kirigaya/jinhui-skills](https://github.com/LSTM-Kirigaya/jinhui-skills)：共享 skills bundle 结构与分发方式参考。
- [linux.do 话题：BetterGPT](https://linux.do/t/topic/1855047)：`BetterGPT` 路由层与默认入口设计参考。
- [wdkns/wdkns-skills](https://github.com/wdkns/wdkns-skills)：另一套公开 skills bundle 组织方式参考。

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
├── agents/
│   ├── code-mapper.toml
│   ├── docs-researcher.toml
│   ├── browser-debugger.toml
│   ├── reviewer.toml
│   ├── search-specialist.toml
│   ├── frontend-developer.toml
│   ├── refactoring-specialist.toml
│   ├── worker.toml
│   ├── explorer.toml
│   └── shell-script-expert.toml
├── skills/
│   ├── BetterGPT/
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
│   ├── frontend-style-mimic/
│   ├── slidev/
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

## 验证

运行下面的命令可以验证仓库结构、安装器和 wrapper 路径解析逻辑：

```bash
python -m unittest discover -s tests
```
