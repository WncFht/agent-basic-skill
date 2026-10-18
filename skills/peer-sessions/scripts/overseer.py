#!/usr/bin/env python3
"""overseer.py — overseer → leaders → subagents 的最小控制面。

子命令：
  spawn <name> <prompt>   起 bg leader（自动挂控制面 hooks + crossSessionInbound:accept）
  ls                      全机会话清单（registry + jobs 合并）
  push <name> <text>      经 messaging socket 直投 user 消息（无 SendMessage 也可用）
  peek <name> [N]         leader transcript 尾部（委托 session-transcripts）
  workers <name>          leader 的 subagent 花名册（委托 session-transcripts）
  policy <name> k v       改 leader 的 control.json（hooks 每事件重读 → 动态策略）
  park <name>             claude stop：摘 job 牌，进程驻留仍可收消息
  kill <name>             SIGTERM pid：真正回收，注册表立即清除
  revive <name>           claude --bg --resume <sid>（原会话还注册时会 fork 副本）

路径约定：~/.claude/overseer/<name>.settings.json / .control.json / .events.jsonl
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
SESSIONS = HOME / ".claude/sessions"
JOBS = HOME / ".claude/jobs"
OVDIR = HOME / ".claude/overseer"
HOOK = Path(__file__).resolve().with_name("leader_hook.py")
TRANSCRIPT = HOME / ".agents/skills/session-transcripts/scripts/session_transcript.py"


def _load_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def registry():
    out = []
    for path in SESSIONS.glob("*.json"):
        try:
            d = _load_json(path)
            d["_file"] = str(path)
            out.append(d)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return out


def jobs():
    out = {}
    for path in JOBS.glob("*/state.json"):
        try:
            d = _load_json(path)
            d["_id"] = path.parent.name
            out[d["_id"]] = d
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return out


def resolve(name):
    """name 或 job-id → (registry_entry | None, job | None)。name 每次现查，不缓存。"""
    for e in registry():
        if e.get("name") == name or e.get("jobId") == name:
            return e, jobs().get(e.get("jobId") or "", None)
    j = jobs().get(name)
    if j:
        for e in registry():
            if e.get("sessionId") == j.get("sessionId"):
                return e, j
        return None, j
    for jid, j in jobs().items():
        if j.get("name") == name:
            for e in registry():
                if e.get("sessionId") == j.get("sessionId"):
                    return e, j
            return None, j
    return None, None


def token_for(pid):
    ks = list(SESSIONS.glob(f"{pid}.*.key"))
    return _load_json(ks[0])["peerToken"] if ks else None


def cmd_spawn(a):
    ent, _ = resolve(a.name)
    if ent:
        sys.exit(
            f"error: '{a.name}' already live (pid {ent['pid']}) — pick another name"
        )
    os.makedirs(OVDIR, exist_ok=True)
    settings = OVDIR / f"{a.name}.settings.json"
    control = OVDIR / f"{a.name}.control.json"

    # 不能用 sys.executable：uv run 下它会指向临时 build venv，spawn 后即失效。
    # leader_hook.py 只用 stdlib，PATH 上的 python3 即可。
    def hookcfg(ev):
        return [{"type": "command", "command": f"python3 {HOOK} {ev} {control}"}]

    with settings.open("w", encoding="utf-8") as sf:
        json.dump(
            {
                "crossSessionInbound": "accept",
                "hooks": {
                    "PreToolUse": [{"matcher": "Agent|Task", "hooks": hookcfg("pre")}],
                    "PostToolUse": [
                        {"matcher": "Agent|Task", "hooks": hookcfg("post")}
                    ],
                    "SubagentStart": [{"hooks": hookcfg("substart")}],
                    "SubagentStop": [{"hooks": hookcfg("substop")}],
                },
            },
            sf,
            indent=2,
        )
    if not control.exists():
        with control.open("w", encoding="utf-8") as cf:
            json.dump(
                {
                    "deny_types": [],
                    "prompt_suffix": "",
                    "worker_directive": "",
                    "block_first_stop": False,
                },
                cf,
                indent=2,
            )
    cmd = ["claude", "--bg", "--name", a.name, "--settings", settings]
    if a.permission_mode:
        cmd += ["--permission-mode", a.permission_mode]
    if a.model:
        cmd += ["--model", a.model]
    cmd.append(a.prompt)
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout + r.stderr)
    if r.returncode == 0:
        print(f"[overseer] control: {control}\n[overseer] settings: {settings}")


def cmd_ls(a):
    seen = set()
    print(f"{'name':<28} {'kind':<12} {'pid':<7} {'status':<8} {'sid8':<10} job")
    for e in sorted(registry(), key=lambda x: x.get("startedAt", 0)):
        print(
            f"{(e.get('name') or '?'):<28} {e.get('kind', '?'):<12} {e.get('pid', '?'):<7} "
            f"{e.get('status', '?'):<8} {(e.get('sessionId') or '')[:8]:<10} {e.get('jobId') or ''}"
        )
        seen.add(e.get("jobId"))
    for jid, j in jobs().items():
        if jid not in seen:
            print(
                f"{(j.get('name') or '?'):<28} {'job(' + (j.get('state') or '?') + ')':<12} {'-':<7} "
                f"{'-':<8} {(j.get('sessionId') or '')[:8]:<10} {jid}"
            )


def cmd_push(a):
    ent, _ = resolve(a.name)
    if not ent:
        sys.exit(f"error: no live session named '{a.name}'")
    tok = token_for(ent["pid"])
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(ent["messagingSocketPath"])
        if tok:
            sock.sendall(json.dumps({"type": "auth", "token": tok}).encode() + b"\n")
            time.sleep(0.2)
        sock.sendall(
            json.dumps(
                {"type": "user", "message": {"role": "user", "content": a.text}}
            ).encode()
            + b"\n"
        )
        time.sleep(0.3)
    print(
        f"pushed to {a.name} (pid {ent['pid']}). 未带身份前缀——建议在 text 里自带 [overseer→{a.name}]。"
    )


def cmd_park(a):
    ent, job = resolve(a.name)
    jid = (job or {}).get("_id") or (ent or {}).get("jobId")
    if not jid:
        sys.exit(f"error: '{a.name}' has no job id (only bg sessions can be parked)")
    print(
        subprocess.run(
            ["claude", "stop", jid], capture_output=True, text=True, check=False
        ).stdout.strip()
    )
    print("note: 进程驻留且仍可收消息；要真正回收用 kill")


def cmd_kill(a):
    ent, _ = resolve(a.name)
    if not ent:
        sys.exit(f"error: no live session named '{a.name}'")
    os.kill(ent["pid"], signal.SIGTERM)
    registry_file = Path(ent["_file"])
    for _ in range(50):
        if not registry_file.exists():
            break
        time.sleep(0.1)
    print(
        f"killed {a.name} (pid {ent['pid']}), registry "
        f"{'cleared' if not registry_file.exists() else 'still present'}"
    )


def cmd_revive(a):
    ent, job = resolve(a.name)
    if ent:
        sys.exit(
            f"error: '{a.name}' still live (pid {ent['pid']}) — resume now would fork a copy"
        )
    sid = (job or {}).get("resumeSessionId") or (job or {}).get("sessionId")
    if not sid:
        sys.exit(f"error: no job record for '{a.name}' — nothing to resume")
    r = subprocess.run(
        ["claude", "--bg", "--resume", sid],
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(r.stdout + r.stderr)


def cmd_policy(a):
    control = OVDIR / f"{a.name}.control.json"
    if not control.exists():
        sys.exit(f"error: {control} not found — was '{a.name}' spawned via overseer?")
    p = _load_json(control)
    try:
        v = json.loads(a.value)
    except json.JSONDecodeError:
        v = a.value
    p[a.key] = v
    with control.open("w", encoding="utf-8") as cf:
        json.dump(p, cf, indent=2, ensure_ascii=False)
    print(
        f"{a.name}: {a.key} = {json.dumps(v, ensure_ascii=False)}  (hooks 下次事件生效)"
    )


def delegate(script_args):
    if not TRANSCRIPT.exists():
        sys.exit(f"error: sibling skill session-transcripts not found at {TRANSCRIPT}")
    os.execvp("uv", ["uv", "run", TRANSCRIPT, *script_args])


def main():
    ap = argparse.ArgumentParser(
        prog="overseer.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("spawn")
    p.add_argument("name")
    p.add_argument("prompt")
    p.add_argument("--model")
    p.add_argument("--permission-mode", default="bypassPermissions")
    p.set_defaults(f=cmd_spawn)
    p = sub.add_parser("ls")
    p.set_defaults(f=cmd_ls)
    p = sub.add_parser("push")
    p.add_argument("name")
    p.add_argument("text")
    p.set_defaults(f=cmd_push)
    p = sub.add_parser("peek")
    p.add_argument("name")
    p.add_argument("tail", nargs="?", default="8")
    p.set_defaults(f=lambda a: delegate(["show", a.name, "--tail", a.tail]))
    p = sub.add_parser("workers")
    p.add_argument("name")
    p.set_defaults(f=lambda a: delegate(["agents", a.name]))
    p = sub.add_parser("policy")
    p.add_argument("name")
    p.add_argument("key")
    p.add_argument("value")
    p.set_defaults(f=cmd_policy)
    p = sub.add_parser("park")
    p.add_argument("name")
    p.set_defaults(f=cmd_park)
    p = sub.add_parser("kill")
    p.add_argument("name")
    p.set_defaults(f=cmd_kill)
    p = sub.add_parser("revive")
    p.add_argument("name")
    p.set_defaults(f=cmd_revive)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
