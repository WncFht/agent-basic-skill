#!/usr/bin/env python3
# echo_lane: terminal {type:data} echoing identity+ctx —— 断言面：
# engine 喂给 lane 的 raw/kind/key/cred_handle 原样吐回 payload。
import json
import sys

req = json.load(sys.stdin)
ctx = req.get("ctx") or {}
ident = req.get("identity") or {}
sys.stdout.write(
    json.dumps(
        {
            "type": "data",
            "payload": {
                "raw": ident.get("raw"),
                "key": ident.get("key"),
                "kind": ident.get("kind"),
                "cred_handle": ctx.get("cred_handle"),
            },
        }
    )
    + "\n"
)
sys.stdout.flush()
