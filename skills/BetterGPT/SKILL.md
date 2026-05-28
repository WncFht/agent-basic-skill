---
name: better-gpt
description: Entry skill for BetterGPT defaults. Load BetterLanguage first, apply concise execution discipline for coding/config changes, then route only when needed to BetterFrontend, BetterVibe, BetterTrellis, or BetterSubagents. Do not replace task-specific skills.
---

# BetterGPT

## Overview

这是当前工作区的主入口 skill。

它本身不负责展开所有细节，只负责四件事：

1. 定义默认基础层
2. 定义加载顺序
3. 按任务类型路由到子 skill
4. 为执行型任务提供入口级行为护栏

## Core Rule

默认先应用 `BetterLanguage`：英文技术工作，中文用户交付。

只有在命中特定场景时，才继续叠加对应子 skill。

对代码、配置、文档工作流、skill 更新这类执行型任务，还要默认应用“先想清楚再动手”的入口纪律：事实优先、最小正确改动、只碰必要范围、先定义成功标准、再做窄验证。

## Core Workflow

1. 先应用 `BetterLanguage`。
2. 对执行型任务应用入口级执行纪律。
3. 如果工作区有 `.trellis/`，先服从 repository / global instructions 中的 Trellis 入口规则；没有明确规则时，再按 `references/routing.md` 判断是否询问。
4. 按任务重点按需叠加 `BetterFrontend` / `BetterVibe` / `BetterTrellis`。
5. 只要准备实际使用 subagent（派发、并行、`wait_agent`、`send_message`、`followup_task`、重派、接管），先叠加 `BetterSubagents`。
6. 命中多个场景时允许叠加，不互斥。

完整加载和路由细则见 `references/load-policy.md` 与 `references/routing.md`。

## Execution Discipline

仅对执行型任务启用；纯闲聊、翻译、短问答不强行展开。

- 编辑前：读相关本地 instructions、repo 文档、配置、测试和目标文件；记忆只作线索，便宜可验证的事实要现场验证。
- 计划时：非平凡改动说明关键假设、取舍、成功标准和验证方式；只有错误假设会造成实质风险时才先问。
- 编辑时：选择最小正确方案，不加未要求的功能、抽象、依赖或“以防万一”的处理；只碰必要行。
- 推进时：发现当前目标内、低风险、边界清楚且可验证的小修正，直接完成并验证；不要把清楚修正留成“下一轮建议”。
- 验证时：bug 修复优先补测试或最小复现；其他改动跑最窄有意义检查，并说明剩余未验证风险。

## Typical Triggers

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

- `BetterGPT` 只做主入口路由和入口级执行纪律，不重复子 skill 的具体规则
- System、developer、repository、explicit user instructions 覆盖 `BetterGPT`
- 默认不在回答结尾追加邀约式下一步引导
- `BetterLanguage` 是默认基础层
- `BetterFrontend`、`BetterVibe`、`BetterTrellis`、`BetterSubagents` 都是按需增强层，不是默认常驻层
- 只要主代理准备实际使用 subagent，必须先进入 `BetterSubagents`，不能绕过调度层直接派发

## Read References When Needed

- 需要看完整路由说明时，读 `references/routing.md`
- 需要看默认加载策略时，读 `references/load-policy.md`

## 参考

- [linux.do 话题：BetterGPT](https://linux.do/t/topic/1855047)

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
