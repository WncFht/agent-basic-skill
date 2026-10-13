#!/usr/bin/env python3
# data_lane: terminal {type:data} — enumerate op, no artifacts
import json
import sys

req = json.load(sys.stdin)
sys.stdout.write(
    json.dumps(
        {
            "type": "data",
            "payload": {
                "rows": [["1", "course-a"], ["2", "course-b"]],
                "raw": req["identity"]["raw"],
            },
        }
    )
    + "\n"
)
sys.stdout.flush()
