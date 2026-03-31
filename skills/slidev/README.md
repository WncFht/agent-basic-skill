# Slidev Skill for Codex

Agent skill that turns Slidev into an end-to-end presentation workflow rather than only a syntax reference.

## What This Skill Covers

- Topic or brief -> researched deck
- Speech or manuscript -> deck with presenter notes
- Report or long document -> analyzed deck
- Card-grid / data-heavy business slides
- Optional SVG hero or diagram assets
- Export to built HTML, PDF, PPTX, PNG, or Markdown

## Workflow Summary

The skill now treats Slidev as the canonical deck source and recommends this pipeline:

1. Intake
2. Research or source analysis
3. Outline
4. Page plan
5. Speaker notes or talk track
6. Asset generation
7. Slidev rendering
8. Verification and export

## Key Files

- `SKILL.md`
  - Main routing and workflow instructions
- `references/`
  - Technical Slidev references plus workflow-specific docs for outline, page planning, speaker notes, SVG, and quality checks
- `scripts/init-slidev-workspace.sh`
  - Initializes a stable deck workspace with `slides.md`, `data/`, `notes/`, and `public/svg/`
- `agents/openai.yaml`
  - UI metadata for the skill

## Typical Use

```text
Use $slidev to research, outline, write, render, and export a complete presentation from this topic, document, or speech draft.
```

## Notes

- Slidev remains the canonical deck format.
- SVG is treated as an optional asset layer, not the primary deck source.
- For factual or time-sensitive slides, preserve sources before writing claims.
