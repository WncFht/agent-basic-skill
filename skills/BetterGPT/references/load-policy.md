# Load Policy

## Goal

把“默认加载”和“按需加载”明确分开，避免所有 skill 都高频常驻。

## Default Layer

- `BetterLanguage`

这是当前唯一默认基础层。

## On-Demand Layer

- `BetterFrontend`
- `BetterVibe`
- `BetterTrellis`
- `BetterSubagents`

只有当前任务明确命中对应场景时，才应叠加。

- 前端展示层任务  
  → `BetterFrontend`
- 全栈架构、职责边界、分层治理任务  
  → `BetterVibe`
- Trellis 初始化、workflow、spec、task、hooks、Codex 接入任务  
  → `BetterTrellis`
- subagent 委派、并行、等待、回收、主代理接管任务  
  → `BetterSubagents`

## Control Principles

- 默认层数量越少越好
- description 越宽，误触发越多
- 默认规则放主入口
- 具体细节放子 skill
- 需要总是生效的规则，不要只靠子 skill 自己触发
- “开发任务是否进入 Trellis 工作流”的入口判断，属于主入口规则，不属于子 skill 自治
- “进入 Trellis 后具体走哪个阶段、用哪个入口”，再交给 `BetterTrellis`

## Practical Meaning

如果你要“BetterGPT 总是加载”，真正可控的方式不是把它放在目录里，而是让上层入口明确先经过它。
