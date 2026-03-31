# Workflow: Report Or Long Document To Deck

Use this route when the source is a PDF, whitepaper, annual report, research paper, transcript, markdown report, or long webpage.

## Stage 1: Ingest

Understand the source before slide generation.

Extract:

- document type
- central thesis or purpose
- key metrics
- important sections
- risks or caveats
- useful figures and tables

## Stage 2: Analysis Layer

Do not render directly from the raw source.

First create an analysis artifact:

- executive summary
- key claims
- metrics and comparisons
- trends
- risks and caveats
- recommendations or conclusions

Store the result in `notes/research.md` and keep source links in `data/sources.md`.

## Stage 3: Card Extraction

For dense documents, especially financial or analytical ones, extract deck-worthy units:

- hero metrics
- comparisons
- trend narratives
- risk bullets
- recommendations
- appendix material

These become candidate cards, charts, or comparison slides.

## Stage 4: Outline And Page Plan

Build the deck in layers:

1. executive framing
2. key findings
3. supporting analysis
4. risks or limitations
5. recommendation or conclusion
6. optional appendix

Then assign each slide a visual pattern in `data/page-plan.json`.

## Stage 5: Render In Slidev

Use Slidev as the deck shell:

- section slides for chapters
- fact or KPI slides for hero metrics
- comparison or two-column slides for contrasts
- card-grid or custom-component slides for dense summary pages
- appendix slides for lower-priority details

## Annual Report And Financial Report Rule

For annual reports and other very long business documents, the recommended route is:

`raw report -> analysis report -> structured cards/charts -> Slidev deck`

Do not treat the raw report as if it were already slide-ready.
