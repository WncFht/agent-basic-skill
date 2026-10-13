#!/usr/bin/env python3
# ctx_lane: echo lane — data 终态把 ctx/identity 回显给测试断言用
# （cred_handle/kind/raw/key 全靠它离开 engine 内部，不进网络）。
import json
import sys

req = json.load(sys.stdin)
sys.stdout.write(
    json.dumps(
        {
            "type": "data",
            "payload": {
                "cred_handle": req["ctx"].get("cred_handle", ""),
                "key": req["identity"].get("key"),
                "kind": req["identity"].get("kind"),
                "raw": req["identity"].get("raw"),
            },
        }
    )
    + "\n"
)
sys.stdout.flush()
