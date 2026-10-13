#!/usr/bin/env python3
# quiet_lane: rc0, no terminal event -> runner synthesizes noresults
import json
import sys

json.load(sys.stdin)
sys.exit(0)
