# Codex Workflow

## Goal

把 Trellis 在 Codex 下的常用工作流整理成顺序感清楚的入口。

## Codex Integration Baseline

Codex 初始化命令：

```bash
trellis init --codex -u <name>
```

官方说明中，Codex 集成会生成：

- 根目录 `AGENTS.md`
- `.agents/skills/`
- `.codex/config.toml`
- `.codex/agents/`
- `.codex/skills/`
- `.codex/hooks/session-start.py`
- `.codex/hooks.json`

这组文件表示 **Codex 自动接入完整**。

但要注意平台差异：

- 在支持 hooks 的平台，这组文件可以代表 hooks 自动接入完整
- 在 **Windows 原生 Codex** 下，不要把它直接等同于“hooks 当前已生效”
- Windows 下当前更稳的口径应是：Codex 主要通过 `AGENTS.md`、skills、文档驱动 workflow 工作，hooks 更偏未来兼容位

如果项目里已经有 `.trellis/`、`AGENTS.md`、`.agents/skills/`，但没有完整 `.codex/*`：

- 仍可判定为 **Trellis 基础可用**
- 只是 SessionStart 自动注入能力不完整
- 回答时不要把这种状态误说成“当前项目不能使用 Trellis”

如果当前是 Windows 原生 Codex：

- 即使 `codex_hooks = true` 已开启，也不要默认把 SessionStart hook 当成当前已运行能力
- 只有在用户明确要验 hooks 实效时，才单独核对该能力

## Session Entry

Codex 侧 Trellis 的核心价值，在不同平台要分开说：

- 支持 hooks 的平台  
  → 可以通过 SessionStart hook 自动注入工作流、指南和任务上下文
- Windows 原生 Codex  
  → 默认更依赖 `AGENTS.md`、skills、文档驱动 workflow，而不是把 SessionStart hook 当成当前已生效能力

因此回答时要先判断：

- hooks 是否真的启用
- 当前会话是否已经在 Trellis 上下文里

## Activation Policy

对用户暴露的入口应是“是否按 Trellis 工作流接管当前开发任务”，而不是先要求用户记住命令名。

默认规则：

1. 用户显式提到 `Trellis`、`start`、`task.py`、`/trellis:*`  
   → 直接进入 Trellis 工作流
2. 用户没有显式提 Trellis，但任务明显是执行型开发任务，且项目存在 `.trellis/`  
   → 只在入口处确认一次是否按 Trellis 工作流推进
3. 一旦确认，本轮后续默认由模型自己判断当前阶段和对应入口
4. 除非用户显式退出，否则不要反复追问是否继续使用 Trellis

## Recommended Command Rhythm

如果当前项目已经接入，官方工作流可以压缩理解成：

1. 进入会话 / 恢复上下文  
   → `start`
2. 开始开发前加载相关规范  
   → `before-dev`
3. 开发过程中按 spec 与 task 推进
4. 做质量检查  
   → `check`
5. 有跨层改动时补做  
   → `check-cross-layer`
6. 完工时整理  
   → `finish-work`
7. 记录会话  
   → `record-session`

## Response Guidance

当用户问“现在该用哪个 Trellis 命令”时，先按阶段回答：

- 刚开工  
  → `start / before-dev`
- 写代码中  
  → 继续围绕当前 task 与 spec
- 做验收  
  → `check / check-cross-layer`
- 要结束本轮  
  → `finish-work / record-session`

## Important Boundary

不同平台的命令外形可能不同，但 Codex 场景里，重点不是死记命令名，而是认清：

- 当前处在 Trellis 生命周期的哪一段
- 当前上下文是来自 spec、task，还是 session log
