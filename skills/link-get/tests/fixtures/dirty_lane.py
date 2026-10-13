#!/usr/bin/env python3
# dirty_lane: emits a non-JSON line mid-stream -> protocol_violation journaled,
# but the lane still completes with a valid terminal.
import json
import os
import sys
from pathlib import Path

req = json.load(sys.stdin)
adir = req["ctx"]["artifact_dir"]
os.makedirs(adir, exist_ok=True)
sys.stdout.write("this is not json\n")  # violation
sys.stdout.write("still not json: {\n")  # violation
p = os.path.join(adir, "dirty.md")
Path(p).write_text("x")
sys.stdout.write(
    json.dumps({"type": "result", "items": [{"path": p, "name": "dirty.md"}]}) + "\n"
)
sys.stdout.flush()
