---
name: deepresearch-skill
description: Create an evidence-backed deep research report and final PDF from multimodal sources such as webpages, PDFs, papers, images, videos, transcripts, code, and structured data. Use when the user wants a polished research deliverable with figures, formulas, tables, clickable links, explicit source provenance, and a compileable LaTeX plus rendered PDF rather than a plain-text summary.
---

# Deep Research Skill

Use this skill to turn a research question plus one or more source modalities into a complete, compileable `.tex` report and a rendered PDF.

Default output pattern: `<preferred-deepresearch-root>/YYYY/MM/DD/<topic-slug>-YYYY-MM-DD/`

Unless the user explicitly asks for another location, create a dedicated report directory under the user's preferred deepresearch root using that tree.

Resolve the preferred deepresearch root from explicit user instructions first, then from memory when available. Keep the final report directory basename in `<topic-slug>-YYYY-MM-DD` form even inside the date tree. Do not hardcode a machine-specific absolute root inside the skill.

## Goal

Produce a research deliverable that is:

- evidence-backed rather than vibes-backed
- grounded in the strongest available primary sources
- visually clear when visuals materially help understanding
- explicit about provenance, uncertainty, and unsupported gaps
- able to stand on its own outside the original chat

The default output is a Chinese report unless the user asks for another language.

## When To Use

Use this skill when the user wants any of the following:

- a deep research report instead of a short answer
- a PDF report with polished layout
- a multimodal synthesis that combines text, PDF, image, video, audio, repo, or data inputs
- richer evidence presentation with screenshots, charts, formulas, tables, or source links
- a deliverable that can be handed to someone else as a standalone document

If the task is only about one video platform and the report should behave like lecture notes, prefer the dedicated video PDF skills first. Use this skill when the job is broader than a single teaching video or when several modalities need to be fused into one research report.

## Core Workflow

### 1. Lock the question and deliverable

Before drafting, resolve:

- the exact research question
- the target reader
- the time horizon or cutoff date
- whether the job is explanation, comparison, due diligence, or recommendation
- whether the final artifact must include `.tex`, PDF, figure assets, appendices, or all of them
- the output directory; default to `<preferred-deepresearch-root>/YYYY/MM/DD/<topic-slug>-YYYY-MM-DD/` unless the user overrides it

If the user or an upstream tool gives an exact absolute output path, obey that path exactly. If you choose the location yourself, resolve the preferred deepresearch root from memory or other local context and follow the default date tree above.

If the scope is underspecified, make the smallest reasonable assumption and state it in the report.

### 2. Build a source ledger before long-form writing

Track at least these fields for every source:

- source id
- modality
- canonical title or label
- author, organization, or channel when known
- URL or local path
- publication date and access date when applicable
- why the source matters
- confidence class such as primary, secondary, or illustrative

Do not start long-form writing until the evidence inventory is credible.

### 3. Read sources in their native modality

Do not flatten everything into plain text too early.

- For PDFs and papers, preserve layout when formulas, tables, or figures matter.
- For images, distinguish what is directly visible from what is inferred.
- For videos, use subtitle-aligned frame search rather than random screenshots.
- For code and datasets, preserve version, commit, or release identity.

Read [references/multimodal-ingestion.md](references/multimodal-ingestion.md) when the task includes more than one modality or when provenance is likely to matter in the final report.

### 4. Build a claim map

For each major claim, know:

- which source or sources support it
- whether those sources agree or conflict
- whether the claim is directly observed, computed, or inferred
- what uncertainty remains

Prefer fewer claims with stronger support over many weakly supported claims.

### 5. Draft from the template

Start from `assets/report-template.tex`.
Set `\reporttheme` early.

If the user explicitly specifies a theme or a strong visual direction, follow that instruction.
If the user does not specify a theme, or only gives a loose preference, choose the theme autonomously based on the topic, report type, evidence density, and packaging needs instead of asking the user to pick from a list.

Treat the theme as a layout decision, not only a color decision. Use stronger packaging metadata only when it materially improves the deliverable rather than by default.

Read [references/theme-selection.md](references/theme-selection.md) when you need fast theme selection guidance.
Read [references/template-usage.md](references/template-usage.md) when you need detailed guidance for the template metadata block, tables, callout boxes, code listings, or packaging fields.

### 6. Write for transfer

Organize the report around evidence, not discovery order.

The report usually contains:

- title page
- executive summary
- source and method overview
- main analysis sections
- comparisons or tables where useful
- a conclusion section
- an appendix with source inventory, detailed notes, or extra figures when needed

Every strong claim, figure, or table should remain traceable.
End the document with a final top-level section such as `\section{结论与后续问题}` that separates:

- what is well supported
- what is likely but not fully proven
- what remains unknown or worth validating next

### 7. Compile and inspect the PDF

Before delivery:

- compile the `.tex` successfully
- check that hyperlinks render correctly
- verify that every figure path resolves
- verify that formulas and tables are legible
- visually inspect the latest rendered PDF instead of trusting the raw source alone
- if any figure or table looks cramped, clipped, overlapping, or visually unbalanced, revise and rebuild

Read [references/report-validation.md](references/report-validation.md) when the report includes many figures, self-drawn charts, or visually dense tables.

## Non-Negotiables

- Prefer the strongest available primary sources for recent, high-stakes, or disputed claims.
- Distinguish direct observation, computation, and inference.
- Keep the URL, path, page number, time interval, version, or commit identity needed to audit the report later.
- Do not emit `[citation needed]`, `[TODO]`, or placeholder links in the final LaTeX.
- Deliver the artifact bundle the task calls for. The default bundle is the final `.tex`, rendered PDF, and the figure assets used by the report, plus appendix assets when they matter to reproducibility.

## Bundled Resources

- `assets/report-template.tex`: default LaTeX template for a research-grade multimodal report
- `references/multimodal-ingestion.md`: modality-specific acquisition and provenance checklist
- `references/theme-selection.md`: fast theme choice guidance
- `references/template-usage.md`: template-specific guidance for metadata, tables, callouts, code listings, and packaging
- `references/report-validation.md`: PDF-level figure, table, and chart validation checklist
