---
name: better-subagents
description: Use for Codex subagent orchestration across callable default, explorer, docs_researcher, reviewer, worker. Map old/framework labels including code-mapper, frontend-developer, browser-debugger, trellis-implement, trellis-check; respect current depth/concurrency limits.
---

# Better Subagents

## Overview

这是主代理的 subagent 调度护栏 skill。

它只负责三件事：

1. 判断是否值得派发
2. 选择当前可调用的 agent 类型
3. 约束等待、纠偏、回收和主代理接管

## Trigger Signals

- 用户提到 subagent、agent、子代理、派发、委派、并行、编排、调度
- 用户在问 `default`、`explorer`、`docs_researcher`、`reviewer`、`worker`
- 用户在问旧能力标签：`code-mapper`、`search-specialist`、`frontend-developer`、`browser-debugger`、`refactoring-specialist`
- 用户在问外部框架 agent 标签：`trellis-implement`、`trellis-check`、`trellis-research`
- 当前任务有多个独立子问题，适合并行
- 子代理等待超时、跑偏、返回不完整或写集冲突

## Core Rule

先判断是否值得派发，再判断派给谁。

- 立即阻塞主路径的本地工作，主代理先做
- 独立、明确、边界清晰的子任务，才派发
- 边界不清、写集冲突、依赖太强时，不并行
- 遵守当前会话和 `~/.codex/config.toml` 的 agent 深度 / 并发限制；当前 `max_depth = 1` 时，子代理不再派生子代理
- 子代理、reviewer 或黑盒测试暴露当前目标内的明确小修正时，主代理吸收证据后直接修并验证，不把清楚修正退回成“下一轮”
- 实际派发前必须说明目标、边界、输出、验证、skill / spec / tool 约束和退出条件

## Callable Agent Map

只把当前 `spawn_agent` 暴露的类型写成 `agent_type`：

- `default`：轻量只读取证、摘要、入口确认
- `explorer`：代码路径、调用链、配置核对、实现入口定位
- `docs_researcher`：OpenAI / Codex 官方文档和 API 语义核验
- `reviewer`：正确性、回归、安全、缺测试风险审查
- `worker`：主代理已明确写集后的本地实现

旧能力标签只能作为任务意图：

- `code-mapper` → `explorer`
- `search-specialist` → `explorer`，轻量非代码任务可用 `default`
- `frontend-developer` → `worker` + `BetterFrontend`
- `refactoring-specialist` → `worker` + `BetterVibe`
- `browser-debugger` → 主代理本地复现；只读代码或日志取证可拆给 `explorer`

外部框架 agent 标签也只能作为任务意图：

- `trellis-implement` → `worker` + `BetterTrellis`，涉及 UI 时再加 `BetterFrontend`
- `trellis-check` → `reviewer` + `BetterTrellis`
- `trellis-research` → `explorer` 或 `docs_researcher`，取决于目标是本地代码证据还是官方文档核验

## Binding Rules

- 前端实现、UI 修复、页面成品化：派 `worker` 时必带 `BetterFrontend`
- 模块拆分、职责治理、低风险重构：派 `worker` 时必带 `BetterVibe`
- Trellis workflow、spec、task、record-session、hooks：派发说明必带 `BetterTrellis`
- 文档核验优先 `docs_researcher`，不要用 `default` / `explorer` 代替
- 风险审查优先 `reviewer`，不要让 `worker` 自审

## Wait And Cleanup

- 只有主线程下一步真的被阻塞时，才 `wait_agent`
- 主线程还有非重叠工作时，先继续推进
- `send_message` / `followup_task` 只用于补边界、纠偏或改道
- 子代理完成且结果已吸收后，立即 `close_agent`
- 多个结果冲突时，主代理回读证据并裁决

## Read References When Needed

- 当前 agent 清单与旧标签映射：`references/agent-registry.md`
- 派发模板、等待、接管细则：`references/dispatch-rules.md`

## Red Flags

- 把旧能力标签误写成当前可派发 agent
- 一拿到任务就先派发，主代理不做关键路径判断
- 派发指令没有目标、边界、输出要求
- 在 `max_depth = 1` 的会话中要求子代理继续派生子代理
- 子代理已经暴露明确、低风险、同范围修正，主代理却只汇报建议不实施
- 多个实现型 agent 修改同一文件或模块
- 子代理完成后长期不关闭
- 频繁给正常工作的子代理发送无效催促消息
