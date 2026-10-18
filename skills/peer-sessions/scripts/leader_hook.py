#!/usr/bin/env python3
"""leader_hook.py — overseer 注入 leader 的控制面 hook。用法见 overseer.py spawn。

事件(参数1): pre(PreToolUse Agent|Task) / post(同) / substart(SubagentStart) / substop(SubagentStop)
控制文件(参数2): JSON，每事件重读 → overseer 改文件即改策略，零对话。

policy 键：
  deny_types        list[str]   这些 subagent_type 的派生直接 deny
  prompt_suffix     str         追加到每个被放行派生的 prompt 尾部（updatedInput 改写）
  worker_directive  str         SubagentStart additionalContext，广播进每个新 worker 上下文
  block_first_stop  bool        每个 worker 首次收工时 block 一次强制复检（同目录 .blocked_<agent> 去重）

所有事件追加写入 <control>.events.jsonl（遥测旁路）。
"""

import datetime
import json
import os
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
control = sys.argv[2] if len(sys.argv) > 2 else ""
try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
try:
    with open(control) as cf:
        policy = json.load(cf)
except Exception:
    policy = {}

try:
    with open(control + ".events.jsonl", "a") as f:
        f.write(
            json.dumps(
                {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "hook": mode,
                    "tool": payload.get("tool_name"),
                    "agent_id": payload.get("agent_id"),
                    "agent_type": payload.get("agent_type"),
                    "input": payload.get("tool_input") or {},
                    "resp_status": (payload.get("tool_response") or {}).get("status"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
except Exception:
    pass

out = {}
if mode == "pre":
    ti = payload.get("tool_input") or {}
    stype = ti.get("subagent_type") or ti.get("subagentType") or ""
    if stype in policy.get("deny_types", []):
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"overseer policy: subagent_type '{stype}' denied",
            }
        }
    elif policy.get("prompt_suffix") and ti.get("prompt"):
        ti2 = dict(ti)
        ti2["prompt"] = ti["prompt"] + policy["prompt_suffix"]
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": ti2,
            }
        }
elif mode == "substart":
    d = policy.get("worker_directive")
    if d:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": d,
            }
        }
elif mode == "substop":
    if policy.get("block_first_stop"):
        flag = control + f".blocked_{payload.get('agent_id') or 'x'}"
        if not os.path.exists(flag):
            try:
                with open(flag, "w") as ff:
                    ff.write("1")
            except Exception:
                pass
            # decision/reason 必须在顶层，塞进 hookSpecificOutput 会被忽略
            out = {
                "decision": "block",
                "reason": "overseer requires a second pass: re-verify your output once, then stop.",
            }

if out:
    print(json.dumps(out, ensure_ascii=False))
sys.exit(0)
