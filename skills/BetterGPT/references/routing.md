# Routing

## Core Goal

让 `BetterGPT` 成为唯一主入口，由它决定默认层和按需层的加载顺序。

## Default Route

- 默认先走 `BetterLanguage`
- 再按固定顺序判断是否叠加其他子 skill

## Current Route

### Language

- `BetterLanguage`
- 角色：默认基础层
- 负责：结构压缩、去口癖、去翻译腔、CLI 分支

### Frontend

- `BetterFrontend`
- 角色：按需增强层
- 负责：前端展示层、视觉约束、成品化、去 AI 味

### Fullstack

- `BetterVibe`
- 角色：按需增强层
- 负责：前端职责边界、后端分层、前后端解耦、全栈可维护性

### Trellis

- `BetterTrellis`
- 角色：按需增强层
- 负责：Trellis 初始化、Codex 软接入、workflow、spec、task、hooks、目录职责解释

### Subagents

- `BetterSubagents`
- 角色：按需增强层
- 负责：subagent 委派、并行、等待、超时介入、结果整合、主代理接管护栏

## Decision Order

主入口按以下顺序判断：

1. 默认先走 `BetterLanguage`
2. 再判当前任务是否属于执行型开发任务  
   → 包括改代码、补功能、修缺陷、重构、补测试、明确落地实现
3. 纯分析、纯代码审查、纯架构讨论、实现前方案比较  
   → 不默认进入 Trellis
4. 如果是执行型开发任务，且项目存在 `.trellis/`  
   → 先做 Trellis 模式判断
5. 只要主代理准备实际使用 subagent（派发、并行、`wait_agent`、`send_input`、重派、接管）  
   → 必须叠加 `BetterSubagents`
6. 再判当前任务重点更偏展示层，还是更偏全栈边界 / 职责拆分
7. 命中多个场景时允许叠加

## Combination Rules

- `BetterLanguage` 永远先于其他 skill
- `BetterTrellis` 是流程层，可与 `BetterFrontend`、`BetterVibe` 叠加
- `BetterSubagents` 是调度层，可与 `BetterTrellis`、`BetterFrontend`、`BetterVibe` 叠加
- `BetterFrontend` 负责展示层成品化
- `BetterVibe` 负责边界、分层、耦合治理
- 纯分析 / 评审 / 方案比较任务，不因存在 `.trellis/` 就默认进入 `BetterTrellis`
- 同时涉及页面产品化与页面 / 模块过载拆分时，叠加 `BetterFrontend` + `BetterVibe`
- 不因为命中一个 skill 就阻断其他必要 skill

## Typical Triggers

- 如果任务重点是“怎么表达”  
  → 只走 `BetterLanguage`

- 如果任务已经是执行型开发，且项目存在 `.trellis/`  
  → 先做 Trellis 模式判断：
  - 用户显式提到 `start`、`task.py`、`record-session`、`/trellis:*`、`Trellis`  
    → 直接进入 `BetterLanguage` + `BetterTrellis`
  - 用户没有显式提 Trellis，但任务明显属于开发执行  
    → 先询问一次是否按 Trellis 工作流推进

- 如果任务重点是“前端长什么样”“页面太像 demo”“要做成正式产品界面”  
  → `BetterLanguage` + `BetterFrontend`

- 如果任务重点是“前后端怎么分层、怎么拆职责、怎么降低耦合”“页面逻辑太重怎么拆”  
  → `BetterLanguage` + `BetterVibe`

- 如果任务重点是“该派给哪个 subagent”“什么时候并行”“`wait_agent` 超时后怎么处理”“主代理何时接管”  
  → `BetterLanguage` + `BetterSubagents`

- 即使用户没有显式提到 subagent，只要主代理已经决定要调用本地 agent  
  → 也必须先进入 `BetterSubagents`，再执行派发

- 如果任务重点是“终端里怎么排版更好读”  
  → 走 `BetterLanguage`，并启用其终端分支

## Boundary

- 主入口不直接复制子 skill 规则
- 子 skill 不应反过来承担主入口路由职责
- 新增子 skill 时，也应先挂到这里，再决定是否独立触发
- “是否切入 Trellis 工作流”由主入口判断
- “切入后如何按阶段执行”由 `BetterTrellis` 判断
- “是否需要进入 subagent 调度层”由主入口判断
- “进入后派给谁、派发格式、等待与接管”由 `BetterSubagents` 判断
