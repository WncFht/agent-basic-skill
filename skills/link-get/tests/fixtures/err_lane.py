#!/usr/bin/env python3
# err_lane: classified terminal error
import json
import sys

json.load(sys.stdin)
sys.stdout.write(
    json.dumps(
        {
            "type": "error",
            "class": "transient",
            "evidence": "fixture 503",
            "retryable": True,
        }
    )
    + "\n"
)
sys.stdout.flush()
