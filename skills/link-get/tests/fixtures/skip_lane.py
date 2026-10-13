#!/usr/bin/env python3
# skip_lane: rc10, no terminal -> skipped/notcovered
import json
import sys

json.load(sys.stdin)
sys.stderr.write("kind not covered\n")
sys.exit(10)
