---
name: better-subagents
description: Use when the task involves subagent selection, delegation strategy, parallel execution, wait and timeout handling, fallback takeover, or how to correctly use the project's local agents together with repository skills and MCP tools. Especially use when the user asks how to orchestrate explorer, worker, reviewer, docs-researcher, code-mapper, frontend-developer, browser-debugger, refactoring-specialist, or other local subagents, or when the main agent needs stronger delegation guardrails.
---

# Better Subagents

## Overview

这是主代理的 subagent 调度护栏 skill。

它不负责重复每个 subagent 的完整说明书，而是负责三件事：

1. 识别当前任务是否值得派发
2. 选择最合适的 subagent 类型
3. 约束主代理如何等待、介入、回收、接管

## Trigger Signals

当请求或上下文出现以下信号时，优先使用本 skill：

- 用户提到 subagent、agent、子代理、派发、委派、并行、编排、调度
- 用户在问 `explorer`、`worker`、`code-mapper`、`reviewer`、`docs-researcher`
- 用户在问“这个任务该派给谁”“什么时候并行”“什么时候主代理自己做”
- 当前任务已经涉及多个独立子问题，适合拆成多个子代理并行
- 当前任务出现等待超时、子代理卡住、返回不完整、写集冲突

## Core Rule

先判断是否真的值得派发，再判断派给谁：

1. 如果当前任务是立即阻塞主路径的本地工作  
   → 主代理先自己做，不急着派发
2. 如果当前任务可以拆成独立、明确、边界清晰的子任务  
   → 再派发给合适 subagent
3. 如果当前任务边界不清、写集冲突、依赖关系太强  
   → 不并行，主代理串行接管

## Boundary First Rule

主代理在派发前，先把子任务压成固定 6 段，不允许裸派发：

1. 任务类型：搜索 / 路径梳理 / 文档核验 / 风险审查 / 前端实现 / 浏览器复现 / 低风险重构 / 通用实现
2. 目标：这次子任务到底要解决什么
3. 边界：只读还是可写；允许哪些文件；禁止碰哪些模块
4. 输出：结论 / 文件列表 / patch / 风险点 / 验证结果
5. 约束：命中的 skill、`.trellis/spec/*`、MCP 分工
6. 退出条件：边界不清、需要改派、卡在权限或依赖时必须回交主代理

如果以上 6 段有两段以上说不清，就不要派发。

## Agent Registry

当前工作区默认可用的本地 subagent 分组如下：

- 调查型  
  → `explorer`、`code-mapper`、`search-specialist`
- 审查 / 核验型  
  → `reviewer`、`docs-researcher`
- 实现型  
  → `worker`、`frontend-developer`、`refactoring-specialist`
- 浏览器取证型  
  → `browser-debugger`

快速映射原则：

- 代码路径、调用链、owner 边界  
  → `code-mapper`
- 快速高信号搜索  
  → `search-specialist`
- 纯只读取证、配置核对、行为确认  
  → `explorer`
- 风险审查、回归、缺测试  
  → `reviewer`
- 官方文档、版本、API 语义核验  
  → `docs-researcher`
- 前端实现、页面修复  
  → `frontend-developer`
- 低风险结构重构  
  → `refactoring-specialist`
- 浏览器复现、前端证据收集  
  → `browser-debugger`
- 没有更合适专用 agent 时  
  → `worker` 作为实现兜底

## Preferred Routing Chains

为减少重叠，默认按以下优先链判断：

- 调用链、ownership、主路径梳理  
  → `code-mapper` 优先，`explorer` 仅只读兜底
- 官方文档、默认值、版本差异、API 语义  
  → `docs-researcher` 优先，`search-specialist` 不替代文档核验
- 前端交互异常且需要复现、抓证据、看浏览器行为  
  → `browser-debugger` 优先，`frontend-developer` 不先抢
- 前端页面实现、组件修复、状态与 UI 调整  
  → `frontend-developer` 优先，`worker` 仅实现兜底
- 低风险结构重构、职责拆分、边界收敛  
  → `refactoring-specialist` 优先，`worker` 不默认承接
- 一般外部资料预筛、找入口、快速缩小范围  
  → `search-specialist` 优先，但不承担文档语义核验和完整调用链梳理

## Default Working Rules

1. 主代理先识别当前任务的关键路径，急迫阻塞项优先本地处理。
2. 只把独立、边界清晰、对主任务有实质推进的子任务派发出去。
3. 读型任务优先派给只读 agent；写型任务优先派给实现型 agent。
4. 多个写型子代理只能在写集不冲突时并行。
5. 派发时必须明确：
   - 目标
   - 边界
   - 预期输出
   - 是否允许修改文件
   - 是否需要验证
6. 如果子任务明显落在某个工作区 skill 的领域内，主代理必须在派发说明中显式带上对应 skill 约束。
7. 如果仓库存在 `.trellis/spec/` 且当前任务能落到对应 spec，主代理必须在派发说明中写明优先参考的 spec 路径。
8. 如果子任务需要外部搜索、文档核验或代码定位，主代理必须在派发说明中写明优先按工作区 MCP 分工使用工具：
   - 外部搜索 → `grok-search`
   - 代码搜索 → `ace-tool`
   - 第三方文档 → `Context7`
   - 已知页面的精确核对 / 官方原文逐页阅读 → 系统 `web`
9. `explorer` / `worker` 是兜底型 agent，不应默认抢占专用 agent 的角色。

补充说明：

- `grok-search` 适合外部资料预筛、多来源归纳、入口发现
- 如果任务已经给出明确 URL，或要求精确引用、逐页确认、原文核对  
  → 不要只停留在 `grok-search` 聚合结果，应优先转到系统 `web`

## Exclusion Rules

为了避免“规范地模糊派发”，主代理还要先判以下排他条件：

- 需要官方文档事实  
  → 不先派 `search-specialist`
- 需要完整调用链 / 边界图  
  → 不先派 `explorer`
- 需要浏览器重现与证据  
  → 不先派 `frontend-developer`
- 需要前端明确实现  
  → 不先派 `browser-debugger`
- 需要低风险结构重构  
  → 不先派 `worker`

只有专用 agent 明确不适配、边界过窄或只是极小补丁时，才允许回退到兜底 agent。

## Skill Binding Rules

常见任务与必须绑定的工作区 skill 如下：

- 前端页面实现、UI 修复、页面成品化  
  → 必带 `BetterFrontend`
- 前后端边界、模块拆分、职责治理、低风险重构  
  → 必带 `BetterVibe`
- Trellis task、spec、workflow、record-session、hooks  
  → 必带 `BetterTrellis`

如果一个子任务同时命中多个领域，允许同时携带多个 skill 约束，但不要遗漏主领域。

## Wait And Intervention Rules

1. 对子代理结果的等待，默认使用 `wait_agent` 语义，不用笼统的“wait”替代。
2. 只有当主线程下一步真的被该子代理结果阻塞时，才应 `wait_agent`。
3. 如果主线程还有可做的非重叠工作  
   → 先继续本地推进，不要一派发就原地等待。
4. 默认等待策略是 **最多 3 轮，每轮 120 秒**；这是一组建议默认值，不是“无限等待”。
5. 第 1 轮 `wait_agent` 超时不等于任务失败，先判断是否只是仍在运行。
6. 如果第 2 轮、第 3 轮后仍无有效进展、或返回内容明显偏题  
   → 主代理应主动检查状态并介入。
7. 介入优先级：
   - 先补充更清晰的边界或目标
   - 再判断是否需要 `send_input`
   - 再判断是否需要中断当前任务并重派
   - 再判断是否关闭子代理并本地接管
8. 如果子代理卡在外部依赖、权限、环境异常  
   → 主代理不要被动一直等待，应直接切回主线程处理阻塞点。
9. 如果多个子代理结果互相冲突  
   → 主代理负责回读证据、裁决冲突、统一结论

## Steer Rules

`send_input` 不是“催一下”的工具，而是纠偏工具。

仅在以下情况才使用：

- 需要补充新的边界、目标或约束
- 发现子代理明显跑偏
- 有新证据会改变原任务方向
- 需要 `interrupt=true` 立即改道

以下情况不要随意追加消息：

- 子代理仍在合理执行窗口内
- 主代理没有新增事实、没有新增边界、没有新的纠偏信息
- 只是想确认“你还在吗”或机械催促进度

## Close And Cleanup Rules

子代理生命周期默认遵循“完成即回收”：

1. 子代理一旦到达 final status，且结果已被主代理读取与整合  
   → 应立即 `close_agent`
2. 不因为“后面可能还会用到”而默认保留已完成子代理
3. 已完成但长期不关闭，会带来：
   - 槽位 / 线程占用
   - 误复用
   - 上下文污染
   - 主线程调度噪音
4. `explorer` / `worker` 这类兜底型 agent 更不应长时间挂起

## Reuse Rules

复用子代理是例外，不是默认。

只有以下情况才允许继续复用原 agent：

- 下一步问题与上一任务高度连续
- 任务边界没有实质变化
- 复用原上下文明显比新开 agent 更稳

以下情况应优先新开 agent，而不是复用：

- 任务类型变了
- skill 绑定变了
- MCP 分工变了
- 从调查切到实现
- 从复现切到修复
- 从文档核验切到代码改动
- 主线程目标已切换

## Thread Budget Rules

`agents.max_threads` 代表并发打开的 agent 线程上限，不是摆设。

因此主代理应遵循：

1. 开多少，就要有计划地回收多少
2. 完成态 agent 不应长期占用线程预算
3. 不要靠保留旧 agent 充当“缓存池”
4. 不要用递归派发或长期挂起来掩盖主代理边界不清的问题

## Read References When Needed

- 需要看当前本地 subagent 清单与角色映射时，读 `references/agent-registry.md`
- 需要看具体派发、等待、接管规则时，读 `references/dispatch-rules.md`

## Hard Constraints

- 不把所有任务都机械地派给子代理
- 不把 urgent blocking work 丢给子代理后原地空等
- 不在写集冲突时并行派发多个实现型 agent
- 不让专用 agent 与 `explorer` / `worker` 长期职责重叠不清
- 不重复抄写各个 agent TOML 里的完整说明书
- 不把“等待超时”直接当成“子代理失败”
- 不在子代理明显卡住时持续被动等待
- 不在实际派发时省略 skill / spec / MCP 约束
- 不让 `explorer` / `worker` 吞掉本应交给专用 agent 的前端、文档核验、浏览器调试或结构重构任务
- 不用“你去看一下这个问题”这类模糊指令直接派发
- 不把搜索、梳理、实现、重构、浏览器复现混成一个子任务
- 不把对子代理的等待写成普通 `wait` 语义，子代理等待要按 `wait_agent` 处理
- 不把 `send_input` 当成催进度按钮
- 不让已完成子代理长期占据后台线程或槽位
- 不在任务边界已经改变后继续复用旧 agent

## Red Flags

- 主代理刚拿到任务就先派发，自己不做关键路径判断
- 明明有专用 agent，却总是只用 `explorer` / `worker`
- 派发指令没有目标、边界、输出要求
- 多个实现型 agent 修改同一文件或同一模块
- 子代理连续超时后，主代理仍然不介入
- 子代理返回结论互相冲突，但主代理没有做证据裁决
- 子代理已经完成，但主代理长时间不关闭
- 主代理频繁给仍在工作中的子代理发送无效催促消息
