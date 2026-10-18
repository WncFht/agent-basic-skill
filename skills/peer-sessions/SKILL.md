---
name: peer-sessions
description: 感知、通知与编排本机其他 Claude Code 会话。当用户要看别的会话在做什么、盯进度、发消息 push 方向，或要搭 overseer→leader→subagent 架构（scripts/overseer.py：spawn/push/observe/policy/kill 全生命周期）时使用。
---

# Peer Sessions

本机每个活着的 Claude Code 进程都在 `~/.claude/sessions/<pid>.json` 注册：name、sessionId、cwd、socket、status（idle/busy）、nameSource。`ListAgents` 和 `claude agents --json --all` 读同一份注册表，后者额外覆盖 `claude --bg` 后台任务（每个任务的 intent、output.result、transcript 路径在 `~/.claude/jobs/<id>/state.json`）。

## 感知

注册表只有状态没有内容。把 name 经 roster 解析成 sessionId 后，用 /session-transcripts 的 `show <sid> --tail N` 读 transcript 尾部，自己判断 working / done / needs_reply / failed——这与 `claude agents` 状态卡背后的 needs_you 分类同构。

## 通知

`SendMessage` 按 name 寻址：

- 对方 idle：消息以 user 角色到达，自动开新 turn 执行。
- 对方 busy：排在 tool call 间隙投递。
- `notify_when_idle: true` 是一次性订阅，对方转 idle 或退出时收到 `[Cross-session idle notice]`。
- 对方看到的信封是 `<cross-session-message from="uds:..." from-name="...">`，并被系统提示告知 peer 消息是输入不是权威；它回复时会抄 `from` 地址再 SendMessage。

## 红线

- **name 每轮重新解析**：会话被重开或复制后身份归新进程，向过期 name 发送直接失败。不缓存 name→目标映射；push 时在消息体里带上目标 sessionId 前 8 位供接收方自证。
- **推送的指令无确认直接执行**：本机会话普遍 bypassPermissions。指令保持窄、可逆，开头带身份前缀（如 `[overseer→a1b2c3d4]`）标明这不是用户本人在说话。
- Push 是请求不是命令：接收方有权评估拒绝，措辞写成可判断的请求。

## Overseer 模式（leader 生命周期控制面）

`SendMessage` 只能寻址已存在的 agent；启停 leader 走 `scripts/overseer.py`（stdlib 单文件，`uv run` 直接跑）：

```
uv run ~/.agents/skills/peer-sessions/scripts/overseer.py <cmd>
  spawn <name> "<prompt>"   # claude --bg + 自动生成控制面 settings/hooks
  ls / peek <name> [N] / workers <name>   # 观察（workers 列出 leader 的 subagent 花名册）
  push <name> "<text>"      # 经 socket 直投 user 消息（overseer 不是会话时也能推）
  policy <name> <k> <v>     # 改 control.json：deny_types/prompt_suffix/worker_directive/block_first_stop
  park / kill / revive <name>
```

**已实测的生命周期语义**（2.1.273）：`spawn` 出的 leader 自动注册进 ListAgents、`SendMessage` 可达；`park`（=`claude stop`）只摘 job 登记**不杀进程**，停完仍能收消息；`kill` 发 SIGTERM 真正回收；`revive`（`--bg --resume`）在原会话还注册时会 fork 副本而非续原 sid。`claude rm <id>` 在本版本会把参数当 prompt 起会话执行——别用，done job 元数据无害。

**控制 leader 的 subagent 管理（零对话）**：spawn 时生成 `--settings` 挂了 4 个 hook（`scripts/leader_hook.py`），每次事件重读 `~/.claude/overseer/<name>.control.json`：

- `deny_types` → `PreToolUse(Agent)` 直接 veto 派生（实测 leader 收到拒绝理由并自行调整）
- `prompt_suffix` → `updatedInput` 静默改写 worker 任务书（实测生效）
- `worker_directive` → `SubagentStart` 注入，广播进每个 worker 上下文（实测生效）
- `block_first_stop` → `SubagentStop` 顶层 `decision:"block"` 强制二次复检（实测生效；注意 decision 必须放顶层，塞进 hookSpecificOutput 会被静默忽略）
- 全部事件落 `<name>.control.json.events.jsonl` = 遥测旁路

**最少干扰原则**：观察一律走文件（`workers`/`peek`/session-transcripts `status`），策略一律走 `policy`+hooks，`push`/`SendMessage` 只用于需要 leader 自己判断的指令。socket 直投的消息以裸 user 行到达、无身份前缀（需 leader spawn 时带 `crossSessionInbound:"accept"`，overseer.py 已内置；否则被 hold 等人审）。

**人类可见性**：bg 会话不占终端但全程可看——`claude agents` TUI 按状态分组 + 一句话摘要 + peek 回复框；`claude attach <id>` 全交互接管（detach 不停会话）。bg 会话编辑前自动进 `.claude/worktrees/` 隔离（`worktree.bgIsolation:"none"` 可关）。
