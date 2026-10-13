#!/usr/bin/env python3
# badterm_lane: emits terminal result then exits 10 -> terminal wins,
# journal must record rc10_after_terminal.
import json
import os
import sys
from pathlib import Path

req = json.load(sys.stdin)
adir = req["ctx"]["artifact_dir"]
os.makedirs(adir, exist_ok=True)
p = os.path.join(adir, "badterm.md")
Path(p).write_text("x")
sys.stdout.write(
    json.dumps({"type": "result", "items": [{"path": p, "name": "badterm.md"}]}) + "\n"
)
sys.stdout.flush()
sys.exit(10)
