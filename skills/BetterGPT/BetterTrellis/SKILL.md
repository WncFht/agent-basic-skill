---
name: better-trellis
description: Use when working with Trellis in Codex, especially for soft integration, project initialization, workflow entry, spec and task organization, hooks, generated command structure, or reducing the need to remember Trellis commands manually. Use when the request mentions Trellis init, Codex integration, workflow, spec, task, workspace logs, hooks, update, onboarding, or agent command mapping.
---

# Better Trellis

## Overview

这是 Trellis 的软接入 skill。

目标不是让模型把一大串命令背下来，而是把 Trellis 在 Codex 下的初始化、进入方式、日常工作流和目录职责整理成稳定入口。

## Trigger Signals

当请求或上下文出现以下信号时，优先使用本 skill：

- 用户提到 `Trellis`
- 用户想在 Codex 里接入 Trellis
- 用户提到初始化、软接入、hooks、workflow、spec、task、workspace
- 用户不想记太多命令，希望按流程工作
- 用户在问 `trellis init`、`trellis update`、`task.py`、`record-session`
- 用户要解释 Trellis 生成的目录和文件分别做什么
- 主入口已经判断当前任务应进入 Trellis 模式

## Core Rule

先区分“基础可用”与“Codex 自动接入完整”这两个层级，再决定后续动作：

1. Trellis 基础可用  
   → 可以继续按 Trellis 工作流回答与推进
2. Codex 自动接入完整  
   → 可以继续强调 hooks / session 注入 / 自动上下文
3. Trellis 基础不可用  
   → 再走初始化代操作流程
4. 用户只是问概念或结构  
   → 只解释，不执行

另外要单独区分：

- **hooks 接入位已生成**
  → 说明 Trellis / Codex 预留了 hooks 相关文件或配置位
- **hooks 当前平台已生效**
  → 只有当前平台真的支持 hooks，且 `hooks.json` / hook 文件可用时，才算已生效

不要把“有 hooks 配置位”直接说成“当前 hooks 正在工作”。

## Mode Activation

`BetterTrellis` 不负责决定“要不要切入 Trellis 模式”这件事本身；那是主入口的职责。

一旦主入口已把当前任务交给 `BetterTrellis`，这里默认按以下规则执行：

1. 用户显式提到 `Trellis`、`start`、`task.py`、`record-session`、`/trellis:*`  
   → 视为已明确进入 Trellis 模式，不再额外确认
2. 用户没有显式提 Trellis，但主入口已确认当前任务要按 Trellis 工作流推进  
   → 只在入口处确认一次
3. 用户确认后，同一任务后续默认持续使用 Trellis 工作流，不重复追问
4. 用户明确拒绝后，本轮回退到普通流程，不再强推 Trellis

## Stage Detection

进入 Trellis 模式后，优先判断当前处在哪个阶段，而不是先给命令表：

1. 只是确认项目能不能用  
   → 回答可用性 / 初始化状态
2. 刚开始一个开发任务  
   → 进入 `start / before-dev / task`
3. 已在开发中  
   → 围绕当前 `task / spec / context` 推进
4. 正在验收或收尾  
   → 进入 `check / finish-work / record-session`

## Initialization First

只要请求涉及“接入 Trellis”或“当前项目能不能开始用 Trellis”，默认先检查：

- `trellis` CLI 是否可用
- 当前项目根目录是否已有 `.trellis/`
- 是否已有基础接入物：
  - `AGENTS.md`
  - `.agents/skills/`
- 是否已有 Codex 自动接入物：
  - `.codex/config.toml`
  - `.codex/hooks/session-start.py`
  - `.codex/hooks.json`

还要额外判断当前平台：

- 如果当前是 **Windows 原生 Codex**
  → 默认按“**hooks 当前平台不作为已生效能力**”处理
  → 这时 Trellis for Codex 主要依赖 `AGENTS.md`、skills、文档驱动 workflow，而不是把 SessionStart hook 当成当前已工作能力
  → 即使 `codex_hooks = true` 已开启，也不要直接推断 hooks 已在 Windows 上生效

判定规则默认如下：

1. 如果 `trellis` CLI 可用，且项目中已有 `.trellis/`  
   → 判定为 **Trellis 基础可用**
2. 如果同时还有 `AGENTS.md`、`.agents/skills/`，但缺少 `.codex/*`  
   → 仍然判定为 **Trellis 可用，但 Codex 自动接入不完整**
3. 如果 `.codex/config.toml`、`.codex/hooks/session-start.py`、`.codex/hooks.json` 也齐全  
   → 判定为 **Trellis for Codex 自动接入完整**
4. 只有在 `.trellis/` 与基础接入物都明显缺失时  
   → 才判定为 **尚未完成 Trellis 初始化**

Windows 原生 Codex 的特殊口径：

- `.codex/hooks/session-start.py`、`.codex/hooks.json` 缺失  
  → 不应直接判定“当前 Windows 项目不可用”
- 如果当前工作流本身依赖 `AGENTS.md` + skills + 文档驱动即可成立  
  → 应判定为 **Trellis 可用，但 hooks 仅为未来兼容占位或未启用能力**
- 只有当用户明确要求“验证 hooks 当前是否真的生效”时，才单独把 hooks 作为当前平台能力核验项

不要把“缺少 `.codex/*`”直接等同于“当前项目不能使用 Trellis”。

只有在判定为“尚未完成 Trellis 初始化”时，才进入初始化代操作流程。

必须先明确告知用户将执行：

```bash
trellis init --codex -u <name>
```

并说明初始化后通常还需要：

- 重新打开当前项目会话
- 检查 `~/.codex/config.toml` 是否已启用：

```toml
[features]
multi_agent = true
codex_hooks = true
```

只有在用户明确确认后，才进入实际初始化。

## Default Working Rules

1. 不把 Trellis 当成一堆零散命令来回答。
2. 优先回答“当前处于哪一阶段”。
3. 已进入 Trellis 模式后，默认由模型自己判断应该使用哪个 Trellis 入口，不把命令选择压力丢给用户。
4. 除了首次入口确认外，不反复问用户“要不要用哪个 Trellis 命令”。
5. 先回答“当前是 Trellis 基础可用，还是 Codex 自动接入完整”，再决定是否需要初始化说明。
6. 优先告诉用户当前阶段和下一步动作，而不是一次性倾倒全部命令。
7. 已初始化项目，优先引导到 `spec / task / workflow / check / record-session` 这几条主线。
8. 解释结构时，要明确区分：
   - `.trellis/` 是工作流与项目知识层
   - `AGENTS.md` 是 Codex 入口层
   - `.agents/skills/` 是共享 skill 层
   - `.codex/` 是 Codex 平台接入层
9. 在 Windows 原生 Codex 下，默认强调 **文档驱动 workflow + skills**，不要把 hooks 当成当前必需已生效项。
10. 需要解释 hooks 时，先说清“当前平台是否支持”，再说“配置位是否存在”。

## Recommended Flow

在 Codex 场景下，默认按这条顺序理解和使用：

1. 初始化项目：`trellis init --codex -u <name>`
2. 写或补 `.trellis/spec/`
3. 需要任务化时，用 `python .trellis/scripts/task.py ...`
4. 进入会话后，按 Trellis 工作流命令推进
5. 完工后做检查与会话记录

不要跳过初始化检查，就直接把后续命令堆给用户。

## Read References When Needed

- 需要处理初始化与代操作流程时，读 `references\init-flow.md`
- 需要给出官方常用命令时，读 `references\commands.md`
- 需要说明 Codex 下的工作流顺序时，读 `references\codex-workflow.md`
- 需要解释 Trellis 目录和 Codex 接入层职责时，读 `references\structure.md`

## Hard Constraints

- 不把 Trellis 回答成“只是另一个 prompts 文件系统”
- 不混淆 `.trellis/`、`AGENTS.md`、`.agents/skills/`、`.codex/` 的职责
- 不在未确认时擅自执行初始化
- 不把所有命令一次性展开给用户制造负担
- 不在已初始化项目里重复指导完整初始化
- 不把“缺少 `.codex/*`”直接说成“当前项目不能使用 Trellis”
- 不把“基础可用”和“Codex 自动接入完整”混成一个状态
- 不把“hooks 接入位存在”与“hooks 当前平台已生效”混成一个状态
- 不在 Windows 原生 Codex 下把 `codex_hooks = true` 直接解释成 SessionStart 已运行
- 不要求用户自己记忆 Trellis 指令名后再继续对话
- 不把“该用哪个 Trellis 命令”当成用户必须先做出的决定
- 用户一旦已确认进入 Trellis 模式，后续默认由模型自动选阶段入口

## Red Flags

- 一上来就罗列大量命令，没有先判断是否已初始化
- 把 Trellis 说成只靠 `AGENTS.md` 生效
- 把 Codex hooks 是否启用这件事漏掉
- 任务明明适合 `task.py`，却仍然让用户手工维持上下文
- 已经有 Trellis 结构，却还按“裸 Codex”方式组织流程
- 已经进入 Trellis 模式，却还反复问用户“要不要用 start / task.py / finish-work”
