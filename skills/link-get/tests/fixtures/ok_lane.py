#!/usr/bin/env python3
# ok_lane: fetch url (or synthesize) -> artifact + result
import json
import os
import sys
import urllib.request
from pathlib import Path

req = json.load(sys.stdin)
ctx = req["ctx"]
adir = ctx["artifact_dir"]
os.makedirs(adir, exist_ok=True)
url = req["identity"]["raw"]


def emit(ev):
    sys.stdout.write(json.dumps(ev) + "\n")
    sys.stdout.flush()


emit({"type": "progress", "msg": "start"})
try:
    if url.startswith("http"):
        data = urllib.request.urlopen(url, timeout=ctx["budget_ms"] / 1000).read()
    else:
        data = b"# fixture article\n"
except Exception as e:
    emit({"type": "error", "class": "transient", "evidence": str(e), "retryable": True})
    sys.exit(0)
p = os.path.join(adir, "article--fixture.md")
Path(p).write_bytes(data)
emit({"type": "artifact", "path": p, "name": "article--fixture.md"})
emit(
    {
        "type": "result",
        "items": [{"path": p, "name": "article--fixture.md", "bytes": len(data)}],
    }
)
