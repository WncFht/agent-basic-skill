# Workflow: Topic Or Brief To Deck

Use this route when the user gives a topic, rough brief, talk idea, class topic, or a speech draft that still needs structure.

## Stage 1: Intake

Capture the minimum useful brief:

- audience
- objective
- length or slide budget
- tone
- what must be included
- what must be avoided
- whether citations are required
- whether speaker notes or a full script are required

Write the result into `notes/intake.md`.

## Stage 2: Research

If the deck includes factual claims, current market facts, technical status, or references:

- browse before writing
- prefer primary sources
- keep a source ledger in `data/sources.md`
- write a compact research summary in `notes/research.md`

## Stage 3: Outline

Turn the brief and research into a deck outline.

Each slide should have:

- a title
- an intent
- one key message
- optional evidence refs
- a suggested layout or pattern

Write this into `data/outline.json`.

## Stage 4: Page Plan

Convert each slide from an idea into an implementation decision:

- what the main block is
- whether the slide is text, chart, comparison, timeline, or card grid
- which slide needs images or SVG
- which slide needs a custom component

Write this into `data/page-plan.json`.

## Stage 5: Speaker Layer

If the deck will actually be presented aloud:

- write per-slide presenter notes
- optionally write `notes/talk-track.md`

Prefer concise presenter notes in `slides.md` comments even when a full talk track also exists.

## Stage 6: Render And Export

Only after the structure is settled:

- implement `slides.md`
- verify in dev server
- export HTML, PDF, PPTX, or PNG as requested

## Failure Pattern To Avoid

Do not start by generating 20 decorated slides from a vague topic. That usually creates a pretty but structurally weak deck that is expensive to fix.
