# Artifact Contract

Use a stable workspace structure so research, planning, rendering, and export do not collapse into one file.

## Recommended Workspace

```text
deck-dir/
├── slides.md
├── components/
├── public/
│   └── svg/
├── data/
│   ├── outline.json
│   ├── page-plan.json
│   └── sources.md
└── notes/
    ├── intake.md
    ├── research.md
    └── talk-track.md
```

## Minimum Meanings

- `slides.md`
  - final Slidev deck source
- `data/outline.json`
  - deck-level structure and slide intents
- `data/page-plan.json`
  - slide-by-slide implementation plan
- `data/sources.md`
  - source ledger with links and short notes
- `notes/intake.md`
  - audience, goal, constraints, style decisions
- `notes/research.md`
  - summary of research and extracted evidence
- `notes/talk-track.md`
  - optional full narration or presenter outline
- `public/svg/`
  - optional generated SVG slide assets
- `components/`
  - reusable Slidev Vue components

## Outline Contract

Prefer a structure like:

```json
{
  "deck_title": "Title",
  "audience": "Who this is for",
  "goal": "What the deck should achieve",
  "slides": [
    {
      "id": "s01",
      "type": "cover",
      "title": "Main title",
      "intent": "Open the deck and frame the thesis",
      "key_message": "One-sentence takeaway",
      "evidence_refs": [],
      "suggested_layout": "cover",
      "speaker_goal": "Hook the audience"
    }
  ]
}
```

## Page Plan Contract

Prefer a structure like:

```json
{
  "slides": [
    {
      "id": "s03",
      "visual_pattern": "bento-kpi-grid",
      "layout_strategy": "custom-component",
      "blocks": [
        { "kind": "hero-number", "content": "32%" },
        { "kind": "mini-card", "content": "Margin improvement" }
      ],
      "assets": ["/svg/profitability-overview.svg"],
      "notes_focus": "Explain why this metric matters now"
    }
  ]
}
```

## Source Ledger Rule

For factual decks, `data/sources.md` should make it easy to answer:

- which source supports which claim
- whether the source is primary or secondary
- whether the source is time-sensitive
- which slide uses it

## Practical Rule

Do not let `slides.md` become a dumping ground for research notes, raw pasted source text, or multiple competing structures.
