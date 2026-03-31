#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <deck-dir>" >&2
  exit 1
fi

deck_dir="$1"

mkdir -p \
  "$deck_dir/components" \
  "$deck_dir/public/svg" \
  "$deck_dir/data" \
  "$deck_dir/notes"

if [ ! -f "$deck_dir/slides.md" ]; then
  cat >"$deck_dir/slides.md" <<'EOF'
---
theme: default
title: Working Title
author: Codex
aspectRatio: 16/9
colorSchema: auto
download: false
drawings:
  enabled: true
  persist: false
---

# Working Title

Subtitle

<!--
Purpose:
Audience:
Goal:
-->

---
layout: section
---

# Section

---
layout: end
---

# Thank You
EOF
fi

if [ ! -f "$deck_dir/data/outline.json" ]; then
  cat >"$deck_dir/data/outline.json" <<'EOF'
{
  "deck_title": "Working Title",
  "audience": "",
  "goal": "",
  "slides": []
}
EOF
fi

if [ ! -f "$deck_dir/data/page-plan.json" ]; then
  cat >"$deck_dir/data/page-plan.json" <<'EOF'
{
  "slides": []
}
EOF
fi

if [ ! -f "$deck_dir/data/sources.md" ]; then
  cat >"$deck_dir/data/sources.md" <<'EOF'
# Sources

- Add links, source type, and the slides that use them.
EOF
fi

if [ ! -f "$deck_dir/notes/intake.md" ]; then
  cat >"$deck_dir/notes/intake.md" <<'EOF'
# Intake

- Audience:
- Goal:
- Slide budget:
- Tone:
- Must include:
- Must avoid:
- Output targets:
EOF
fi

if [ ! -f "$deck_dir/notes/research.md" ]; then
  cat >"$deck_dir/notes/research.md" <<'EOF'
# Research

- Key findings:
- Evidence:
- Open questions:
EOF
fi

if [ ! -f "$deck_dir/notes/talk-track.md" ]; then
  cat >"$deck_dir/notes/talk-track.md" <<'EOF'
# Talk Track

Use this file for the full narration when the deck needs a script.
EOF
fi

echo "Initialized Slidev workspace at: $deck_dir"
