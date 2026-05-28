---
name: better-trellis
description: Use for Trellis workflow in Codex, including project initialization, spec/task organization, hooks, workspace logs, and command mapping. Focus on stage detection and safe workflow entry; do not dump command lists by default.
---

# Better Trellis

## Overview

这是 Trellis 的 Codex 软接入 skill。

目标是让主代理判断当前 Trellis 阶段并选择入口，而不是把命令表丢给用户。

## Trigger Signals

- 用户提到 `Trellis`
- 用户想在 Codex 里接入 Trellis
- 用户提到初始化、workflow、spec、task、workspace、hooks
- 用户在问 `trellis init`、`trellis update`、`task.py`、`$start`、`continue`、`$finish-work`、`record-session`
- 主入口已经判断当前任务应进入 Trellis 模式

## Core Rule

先判断状态，再决定动作：

- Trellis 基础可用：继续按 Trellis 工作流推进
- Codex 接入文件完整：可说明 skills / agents / hooks 接入位齐全
- Trellis 基础不可用：再走初始化代操作流程
- 用户只是问概念或结构：只解释，不执行

明确区分：

- hooks 接入位已生成：存在配置位或文件
- hooks runtime 已验证：当前平台真的支持并正在加载 hook

不要把“有 hooks 配置位”说成 runtime 已验证，也不要只因接入文件齐全就宣称 session injection 已生效。

## Mode Activation

`BetterTrellis` 不决定是否进入 Trellis 模式；主入口负责这个判断。

进入后按阶段处理：

1. 确认项目能否使用 Trellis
2. 会话或上下文恢复：进入 `$start` / `start`
3. 开发中：围绕当前 `task / spec / context` 推进，必要时用 `continue`
4. 验收或检查：进入 `check`
5. 完工记录：进入 `$finish-work` / `finish-work` / `record-session`

用户已明确提到 `Trellis`、`$start`、`start`、`continue`、`task.py`、`record-session` 或平台原生命令时，不再重复确认。

## Initialization Check

涉及“接入 Trellis”或“当前项目能不能用 Trellis”时，先检查：

- `trellis` CLI 是否可用
- 当前项目根目录是否已有 `.trellis/`
- 是否有基础接入物：`AGENTS.md`、`.agents/skills/`
- 是否有 Codex 接入目录：`.codex/agents/`、`.codex/skills/`、`.codex/hooks/`
- 只有诊断 hooks 时，再细查 `.codex/hooks/session-start.py`、`.codex/hooks.json` 和全局 feature flag

判定口径：

- 有 CLI + `.trellis/`：Trellis 基础可用
- 有 `.trellis/` + 基础接入物但缺 `.codex/*`：Trellis 可用，但 Codex 接入文件不完整
- `.codex/*` 也齐全：Trellis for Codex 接入文件完整
- `.trellis/` 与基础接入物都明显缺失：尚未初始化

Windows 原生 Codex 下，不把缺少 `.codex/*` 直接判成不可用；默认按文档驱动 workflow + skills 处理。

## Init Safety

只有判定为尚未初始化时，才进入初始化代操作流程。

执行前必须先说明将运行：

```bash
trellis init --codex -u <name>
```

并提醒初始化后通常要重新打开项目会话、检查 Codex features。

未得到用户明确确认，不执行初始化。

## Read References When Needed

- 初始化与代操作：`references/init-flow.md`
- 常用命令：`references/commands.md`
- Codex 工作流顺序：`references/codex-workflow.md`
- 目录职责：`references/structure.md`

## Red Flags

- 一上来罗列大量命令，没有先判断阶段
- 把 Trellis 说成只靠 `AGENTS.md` 生效
- 混淆 `.trellis/`、`AGENTS.md`、`.agents/skills/`、`.codex/`
- 把“基础可用”和“Codex 接入文件完整”混成一个状态
- 把“hooks 接入位存在”和“hooks runtime 已验证”混成一个状态
- 已进入 Trellis 模式后，还反复问用户该用哪个命令
