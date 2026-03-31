---
name: slidev
description: Research, outline, write, render, and export end-to-end presentations with Slidev, including speech notes, web-sourced evidence, charts, optional SVG slide assets, and HTML/PDF/PPTX outputs. Use when the user wants a full PPT-style deck from a topic, manuscript, report, or existing slides, especially for technical talks, tutorials, internal reviews, and data-heavy presentations.
---

# Slidev - End-to-End Presentation Workflow

Use Slidev as the canonical deck source when the result should stay editable as Markdown/Vue and export cleanly to HTML, PDF, PPTX, or PNG.

Do not jump straight from a topic to `slides.md`. Keep planning and evidence in intermediate artifacts first, then render the deck once the structure is defensible.

## Core Principles

1. Canonical deck first
   - `slides.md` is the maintained source of truth for the final presentation.
   - HTML, PDF, PPTX, PNG, and presenter mode are exports or runtime views of that deck.
2. Separate thinking from rendering
   - Do research, outlining, page planning, and speaker-note writing before detailed slide implementation.
3. One slide, one job
   - Each slide should make one claim, answer one question, or perform one transition.
4. Evidence before decoration
   - For factual decks, search first, preserve sources, then write claims.
5. Speaker notes are first-class
   - If the user wants a talk, lecture, or pitch, write presenter notes and optionally a full talk track.
6. SVG is an optional asset layer
   - Use SVG for hero slides, diagrams, or editable visual assets, but keep Slidev as the canonical deck format.
7. Verify in browser and export for the requested target
   - Always run the deck, inspect it, then export the required formats.

## When To Use

- New presentation from a topic, brief, or prompt
- Speech or manuscript -> deck
- Report, paper, annual report, or long document -> deck
- Existing Slidev deck enhancement, restructuring, or export
- Technical, educational, or data-heavy presentations that benefit from citations, charts, diagrams, notes, or code examples

## Deliverable Model

Treat the deck as a small pipeline, not a single file:

- Source and evidence artifacts
- Outline and page-plan artifacts
- Slidev deck source
- Optional assets such as SVG, charts, and images
- Final exports such as HTML, PDF, PPTX, PNG

Read [references/artifact-contract.md](references/artifact-contract.md) before starting a substantial deck from scratch.

## Route Selection

Choose the lightest route that still preserves quality.

### Mode A: Topic Or Brief -> Deck

Use when the user provides a topic, audience, goal, rough notes, or a few seed links.

Read:

- [references/workflow-topic-to-deck.md](references/workflow-topic-to-deck.md)
- [references/artifact-contract.md](references/artifact-contract.md)
- [references/prompt-templates.md](references/prompt-templates.md)

### Mode B: Speech, Manuscript, Or Teaching Script -> Deck

Use when the user already has a speech draft, article, lecture notes, or a talk narrative.

Read:

- [references/workflow-topic-to-deck.md](references/workflow-topic-to-deck.md)
- [references/speaker-notes-and-script.md](references/speaker-notes-and-script.md)
- [references/artifact-contract.md](references/artifact-contract.md)

### Mode C: Report Or Long Document -> Deck

Use when the input is a PDF, annual report, whitepaper, analysis report, notebook, transcript, or webpage dump.

Read:

- [references/workflow-document-to-deck.md](references/workflow-document-to-deck.md)
- [references/artifact-contract.md](references/artifact-contract.md)
- [references/prompt-templates.md](references/prompt-templates.md)

### Mode D: Existing Slidev Deck -> Enhancement Or Export

Use when `slides.md` or a Slidev project already exists.

Read:

- [references/deck-quality-checks.md](references/deck-quality-checks.md)
- the relevant technical reference files for the requested change

## Phase 1: Preflight

Before writing slides:

1. Confirm the canonical output directory.
2. Confirm the requested outputs:
   - Slidev deck only
   - built HTML
   - PDF
   - PPTX
   - PNG
   - optional SVG assets
3. Confirm whether the deck needs:
   - citations or source links
   - speaker notes or full talk track
   - charts, diagrams, or code samples
   - brand or style constraints
4. If internet research is required:
   - browse before writing factual claims
   - prefer primary or official sources for technical or time-sensitive facts
   - preserve source links in the workspace
5. If the deck is new, initialize the workspace with:

```bash
scripts/init-slidev-workspace.sh <deck-dir>
```

If a real Slidev project does not exist yet, create one first:

```bash
pnpm create slidev
```

If `slidev` is not available globally, prefer project-local commands:

```bash
pnpm exec slidev dev
pnpm exec slidev build
pnpm exec slidev export
```

## Phase 2: Gather Inputs And Sources

### For topic-driven decks

Capture:

- audience
- deck goal
- talk length or slide budget
- tone and level of formality
- required sections
- forbidden claims or constraints
- references the user already trusts

### For manuscript-driven decks

Segment the manuscript into speaking beats:

- opening
- framing
- key arguments
- evidence blocks
- transitions
- closing

Then map those beats to slide intentions before writing any slides.

### For report or long-document decks

Do not render directly from the raw document.

First produce a usable analysis layer:

- summary
- key claims
- metrics
- comparisons
- risks
- recommendations
- source ledger

For annual reports or similar data-heavy inputs, the recommended route is:

`document -> analysis -> card extraction -> slide plan -> Slidev deck`

## Phase 3: Build The Outline

Produce an outline artifact before `slides.md` becomes large.

Minimum expectations:

- deck title
- audience
- goal
- slide list
- each slide's title
- each slide's intent
- key message per slide
- evidence refs per slide when factual
- suggested layout or component pattern

Prefer structured artifacts such as `data/outline.json`.

Use the outline prompt patterns in [references/prompt-templates.md](references/prompt-templates.md) when useful.

## Phase 4: Build The Page Plan

Convert the outline into page-level implementation decisions.

For each slide, decide:

- slide type
- visual pattern
- major blocks
- what belongs in a chart, table, card, diagram, or note
- whether a custom component is needed
- whether an SVG asset is worth generating
- what the speaker should accomplish on this slide

For layout mapping and card-heavy business slides, read:

- [references/layout-patterns-business.md](references/layout-patterns-business.md)

Do not rely only on built-in layouts for complex data or business slides. Use local components in `components/` when the slide has repeated card, KPI, chart, or citation structures.

## Phase 5: Write Speaker Notes And Talk Track

If the user wants a real talk, lecture, pitch, or teachable deck:

- write presenter notes for each slide
- optionally write a full talk track in `notes/talk-track.md`
- keep the final slide notes inside `slides.md` as HTML comments

Notes should cover:

- why the slide exists
- the opening line
- 2-4 speaking beats
- transition out
- optional timing cue

Read [references/speaker-notes-and-script.md](references/speaker-notes-and-script.md).

## Phase 6: Generate Assets

Use the lightest asset strategy that fits the slide.

### Charts And Diagrams

- Use Mermaid, PlantUML, LaTeX, or Chart.js-equivalent screenshots only when they improve understanding.
- Keep raw data or formulas in the workspace.

### Images

- Put reusable deck assets in `public/`.
- Prefer locally copied or generated assets over fragile remote URLs unless caching behavior is acceptable.

### SVG

Use SVG when the slide needs:

- an editable hero stat page
- an architecture or process diagram
- a polished single-slide visual asset
- an Office-friendly asset outside Slidev

Read [references/svg-slide-assets.md](references/svg-slide-assets.md).

Keep SVG assets under `public/svg/` and reference them from Slidev slides.

## Phase 7: Render In Slidev

Use Slidev features intentionally:

- built-in layouts for simple slides
- custom local components for repeated business patterns
- Markdown for normal content
- MDC or raw HTML only when it clearly simplifies layout work
- scoped styles for slide-local visual control
- deck headmatter for export, presenter, fonts, and aspect-ratio configuration

Read these references on demand:

- [references/core-syntax.md](references/core-syntax.md)
- [references/core-headmatter.md](references/core-headmatter.md)
- [references/core-frontmatter.md](references/core-frontmatter.md)
- [references/core-layouts.md](references/core-layouts.md)
- [references/core-components.md](references/core-components.md)
- [references/syntax-mdc.md](references/syntax-mdc.md)
- [references/core-animations.md](references/core-animations.md)
- [references/style-scoped.md](references/style-scoped.md)

Implementation guidance:

1. Start with headmatter and deck structure.
2. Implement section dividers and skeleton slides first.
3. Add complex slides with components or scoped CSS.
4. Add presenter notes after slide bodies stabilize.
5. Add optional motion last.

## Phase 8: Verify And Export

Always verify in the browser before exporting.

### Smoke Test

Run:

```bash
pnpm exec slidev dev
```

Confirm:

- slides render correctly
- no broken components
- no missing images or SVGs
- notes and click flows behave as intended
- dense slides remain readable at 16:9

Read [references/deck-quality-checks.md](references/deck-quality-checks.md).

### Build HTML

Use:

```bash
pnpm exec slidev build
```

This is the primary HTML export path.

### Export PDF, PPTX, PNG, Or Markdown

Use:

```bash
pnpm exec slidev export
pnpm exec slidev export --format pptx
pnpm exec slidev export --format png
pnpm exec slidev export --format md
```

For export details, read:

- [references/core-cli.md](references/core-cli.md)
- [references/core-exporting.md](references/core-exporting.md)

If export fails because the browser runtime is missing:

```bash
pnpm add -D playwright-chromium
npx playwright install chromium
```

## Workflow Priorities

Default priority order:

1. credible structure
2. factual accuracy and sources
3. readable slide density
4. speaker usefulness
5. visual polish
6. export success

Do not sacrifice 1-4 just to make the deck prettier.

## Supporting Files

| File | Purpose | When to Read |
|------|---------|-------------|
| [references/artifact-contract.md](references/artifact-contract.md) | Canonical workspace files and JSON contracts | Before new decks |
| [references/workflow-topic-to-deck.md](references/workflow-topic-to-deck.md) | Route for topic, brief, and speech driven decks | Mode A or B |
| [references/workflow-document-to-deck.md](references/workflow-document-to-deck.md) | Route for reports, PDFs, and long documents | Mode C |
| [references/layout-patterns-business.md](references/layout-patterns-business.md) | Mapping slide intent to Slidev layout and component patterns | Page planning |
| [references/speaker-notes-and-script.md](references/speaker-notes-and-script.md) | Presenter notes and talk-track rules | Decks with narration |
| [references/svg-slide-assets.md](references/svg-slide-assets.md) | When and how to use SVG assets with Slidev | SVG generation requested |
| [references/prompt-templates.md](references/prompt-templates.md) | Reusable prompt skeletons for outline, analysis, talk track, and SVG | When model assistance is needed |
| [references/deck-quality-checks.md](references/deck-quality-checks.md) | Verification and acceptance checklist | Before delivery |
| [references/core-syntax.md](references/core-syntax.md) | Markdown syntax | During implementation |
| [references/core-headmatter.md](references/core-headmatter.md) | Deck-wide config | During implementation |
| [references/core-frontmatter.md](references/core-frontmatter.md) | Per-slide config | During implementation |
| [references/core-layouts.md](references/core-layouts.md) | Built-in layouts | During implementation |
| [references/core-components.md](references/core-components.md) | Built-in components and auto-import rules | During implementation |
| [references/core-animations.md](references/core-animations.md) | Click and motion patterns | When motion helps |
| [references/core-cli.md](references/core-cli.md) | Dev/build/export commands | Verification and export |
| [references/core-exporting.md](references/core-exporting.md) | Export options and troubleshooting | Verification and export |
| [scripts/init-slidev-workspace.sh](scripts/init-slidev-workspace.sh) | Deterministically create the working artifact structure | Before a new deck |
