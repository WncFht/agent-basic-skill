#!/usr/bin/env python3
# escape_lane: declares an artifact outside artifact_dir -> collect must reject
import json
import os
import sys
import tempfile
from pathlib import Path

req = json.load(sys.stdin)
adir = req["ctx"]["artifact_dir"]
os.makedirs(adir, exist_ok=True)
outside = os.path.join(tempfile.gettempdir(), "escape-artifact.md")
Path(outside).write_text("escaped")
inside = os.path.join(adir, "legit.md")
Path(inside).write_text("ok")
sys.stdout.write(
    json.dumps(
        {
            "type": "result",
            "items": [
                {"path": outside, "name": "escape.md"},
                {"path": inside, "name": "legit.md"},
            ],
        }
    )
    + "\n"
)
sys.stdout.flush()
