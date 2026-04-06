---
name: better-gpt
description: Use as the workspace-level entry skill for this repository when responses should follow BetterGPT defaults. This skill routes by default to BetterLanguage for language shaping, then applies task-specific enhancements only when needed, such as BetterFrontend for frontend presentation work, BetterVibe for full-stack engineering boundary and maintainability guidance, BetterTrellis for Trellis workflow, Codex soft integration, initialization, spec, task, and hooks-related guidance, and BetterSubagents for subagent delegation, orchestration, wait handling, and takeover guardrails. Use when a single main entry skill should coordinate default loading order and on-demand sub-skill activation.
---

# BetterGPT

## Overview

这是当前工作区的主入口 skill。

它本身不负责展开所有细节，只负责三件事：

1. 定义默认基础层
2. 定义加载顺序
3. 按任务类型路由到子 skill

## Core Rule

默认先应用 `BetterLanguage`。

只有在命中特定场景时，才继续叠加对应子 skill。

## Load Order

默认顺序如下：

1. 先进入 `BetterGPT`
2. 默认应用 `BetterLanguage`
3. 再判断当前任务是否是执行型开发任务；若工作区存在 `.trellis/`，先做 Trellis 模式判断
4. 再判断任务重点属于展示层，还是工程边界 / 职责拆分
5. 命中展示层任务时叠加 `BetterFrontend`
6. 命中全栈边界、分层、耦合治理任务时叠加 `BetterVibe`
7. 命中 Trellis 初始化、工作流、spec、task、hooks、Codex 软接入问题时叠加 `BetterTrellis`
8. 只要主代理准备实际派发、并行调度、等待、重派、接管 subagent，也必须叠加 `BetterSubagents`
9. 如果当前是 CLI 场景，则由 `BetterLanguage` 内部环境分支决定终端排版

## Routing Rules

### Decision Order

按以下顺序判断：

1. 默认先应用 `BetterLanguage`
2. 判断当前任务是否属于执行型开发任务  
   → 这里默认指改代码、补功能、修缺陷、重构、补测试、明确落地实现
3. 纯分析、纯代码审查、纯架构讨论、实现前方案比较  
   → 不默认进入 Trellis
4. 如果是执行型开发任务，且工作区存在 `.trellis/`  
   → 先做 Trellis 模式判断，再决定是否叠加 `BetterTrellis`
5. 只要主代理准备实际使用 subagent（包括派发、并行、`wait_agent`、`send_input`、重派、接管）  
   → 必须叠加 `BetterSubagents`
6. 再判断任务重点更偏展示层，还是更偏工程边界 / 职责拆分
7. 命中多个场景时允许叠加，不互斥

### Combination Rules

- `BetterLanguage` 永远先于其他 skill
- `BetterTrellis` 是流程层，可与 `BetterFrontend`、`BetterVibe` 叠加
- `BetterSubagents` 是调度层，可与 `BetterTrellis`、`BetterFrontend`、`BetterVibe` 叠加
- `BetterFrontend` 负责展示层成品化，不负责全栈边界治理
- `BetterVibe` 负责职责拆分和工程边界，不负责 Trellis 工作流接入
- 纯分析、纯评审、纯方案比较任务，不因项目存在 `.trellis/` 就默认触发 `BetterTrellis`
- 如果任务同时涉及“页面产品化”和“页面 / 模块过载拆分”，则同时叠加 `BetterFrontend` + `BetterVibe`
- 不因为命中一个 skill 就阻断其他必要 skill

### Typical Triggers

- 普通对话、分析、解释、表达优化  
  → 默认只走 `BetterLanguage`
- “开始做这个功能”“现在实现这个需求”“创建 task”“task.py”“record-session”“/trellis:*”  
  → 优先做 Trellis 判断，命中则叠加 `BetterTrellis`
- “这个页面太像 demo”“做成正式产品 UI”“去掉原型感 / AI 味”  
  → `BetterLanguage` + `BetterFrontend`
- “这个页面逻辑太重怎么拆”“service 太臃肿怎么分层”“前后端边界怎么定”  
  → `BetterLanguage` + `BetterVibe`
- “这个任务该派给哪个 subagent”“什么时候并行”“子代理超时怎么接管”  
  → `BetterLanguage` + `BetterSubagents`
- 即使用户没提 subagent，只要主代理已经决定要实际派发 `explorer` / `worker` / 其他本地 agent  
  → 也必须进入 `BetterLanguage` + `BetterSubagents`

## Hard Constraints

- `BetterGPT` 只做路由，不重复子 skill 的具体规则
- 默认不在回答结尾追加邀约式下一步引导
- 这条规则属于全局表达约束，不只由子 skill 自行决定
- 如果当前是执行型开发任务，且工作区已有 `.trellis/`，主入口必须先判断是否进入 Trellis 工作流
- 这类入口判断属于主路由职责，不能只依赖 `BetterTrellis` 自己触发
- 用户一旦明确确认本轮按 Trellis 工作流推进，后续同一任务默认持续按 Trellis 处理，不反复询问
- 如果用户明确拒绝本轮使用 Trellis，才回退为普通开发流程
- 只要主代理准备实际使用 subagent，必须先进入 `BetterSubagents`，不能绕过调度层直接派发
- 进入 `BetterSubagents` 后，派发说明必须带上子任务边界、预期输出、验证要求，以及命中的 skill / spec / MCP 约束
- `BetterLanguage` 是默认基础层
- `BetterFrontend` 是按需增强层，不是默认常驻层
- `BetterVibe` 是按需增强层，不是默认常驻层
- `BetterTrellis` 是按需增强层，不是默认常驻层
- `BetterSubagents` 是按需增强层，不是默认常驻层
- 如果一个任务不属于前端，就不要加载 `BetterFrontend`
- 如果一个任务不属于全栈边界或工程分层，就不要加载 `BetterVibe`
- 如果一个任务不属于 Trellis 工作流或软接入，就不要加载 `BetterTrellis`
- 如果一个任务不属于 subagent 调度、委派、等待、接管，就不要加载 `BetterSubagents`

## Read References When Needed

- 需要看完整路由说明时，读 `references\routing.md`
- 需要看默认加载策略时，读 `references\load-policy.md`

## Important Boundary

仅靠目录结构，不能天然保证“总是加载”。

如果要让 `BetterGPT` 真正成为默认入口，需要在更高层明确引用它，例如：

- 工作区 AGENTS
- 当前会话显式调用
- 其他上层固定入口配置

## Red Flags

- 主入口开始重复写子 skill 的细节
- 一个普通任务同时误触发多个子 skill
- `BetterFrontend` 被当成默认层长期常驻
- `BetterVibe` 被当成默认层长期常驻
- `BetterTrellis` 被当成默认层长期常驻
- `BetterLanguage` 没有先于其他子 skill 生效
