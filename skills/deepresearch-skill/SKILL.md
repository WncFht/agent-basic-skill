---
name: deepresearch-skill
description: Create an evidence-backed deep research report and final PDF from multimodal sources such as webpages, PDFs, papers, images, videos, transcripts, code, and structured data. Use when the user wants a polished research deliverable with figures, formulas, tables, clickable links, explicit source provenance, and a compileable LaTeX plus rendered PDF rather than a plain-text summary.
---

# Deep Research Skill

Use this skill to turn a research question plus one or more source modalities into a complete, compileable `.tex` report and a rendered PDF.

Default output root: `/home/fanghaotian/Desktop/src/deepresearch`

Unless the user explicitly asks for another location, create a dedicated report directory under that root using this tree:

`/home/fanghaotian/Desktop/src/deepresearch/YYYY/MM/DD/<topic-slug>-YYYY-MM-DD/`

Keep the final report directory basename in `<topic-slug>-YYYY-MM-DD` form even inside the date tree. Do not flat-dump reports directly under `/home/fanghaotian/Desktop/src/deepresearch/`.

## Goal

Produce a research deliverable that is:

- evidence-backed rather than vibes-backed
- grounded in the strongest available primary sources
- enriched by the right modalities, not text alone
- visually clear, with images, tables, formulas, diagrams, and links when they improve understanding
- explicit about provenance, uncertainty, and unsupported gaps

The default output is a Chinese report unless the user asks for another language.

## When To Use

Use this skill when the user wants any of the following:

- a deep research report instead of a short answer
- a PDF report with polished layout
- a multimodal synthesis that combines text, PDF, image, video, audio, repo, or data inputs
- richer evidence presentation with screenshots, charts, formulas, tables, or source links
- a deliverable that can be handed to someone else as a standalone document

If the task is only about one video platform and the report should behave like lecture notes, prefer the dedicated video PDF skills first. Use this skill when the job is broader than a single teaching video or when several modalities need to be fused into one research report.

## Workflow

### 1. Lock the research question and deliverable

Before drafting, resolve:

- the exact research question
- the target reader
- the time horizon or cutoff date
- whether the user wants explanation, comparison, due diligence, or recommendation
- whether the final artifact must include `.tex`, PDF, figure assets, appendices, or all of them
- the output directory; default to `/home/fanghaotian/Desktop/src/deepresearch/YYYY/MM/DD/<topic-slug>-YYYY-MM-DD/` unless the user overrides it

If the user or an upstream tool gives an exact absolute output path, obey that path exactly. If you choose the location yourself, follow the default tree above.

If the scope is underspecified, make the smallest reasonable assumption and state it in the report.

### 2. Build an evidence inventory before writing

Create a working source ledger with one row per source:

- source id
- modality: web, paper, PDF, image, video, audio, code, data, interview, note
- canonical title or label
- author, organization, or channel when known
- URL or local path
- publication date and access date when applicable
- why the source matters
- confidence level: primary, secondary, illustrative

Do not start long-form writing until the evidence inventory is credible.

### 3. Read every source in its native modality first

Do not flatten everything into plain text too early.

- For PDFs and papers, preserve layout-aware extraction when formulas, tables, or figures matter.
- For images, distinguish what is directly visible from what is inferred.
- For videos, use subtitle-aligned frame search rather than random screenshots.
- For code and datasets, preserve version or commit identity.

Read [references/multimodal-ingestion.md](references/multimodal-ingestion.md) when the task includes more than one modality or when provenance is likely to matter in the final report.

### 4. Synthesize claims with explicit support

For each major claim, know:

- which source or sources support it
- whether those sources agree or conflict
- whether the claim is directly observed, computed, or inferred
- what uncertainty remains

Prefer fewer claims with stronger support over many weakly supported claims.

### 5. Draft the report from the template

Start from `assets/report-template.tex`.
Prefer the template's default `LXGW`-first font setup for Chinese report text unless the user explicitly asks for another type direction.
Set `\reporttheme` in the metadata block before writing the body.
The bundled starter themes are `warm-academic`, `nord-frost`, `github-light`, `solarized-light`, `paper-classic`, `ocean-breeze`, `tufte`, `classic-thesis`, `ieee-journal`, `elegant-book`, `chinese-red`, and `ink-wash`.
Default to the lighter print-safe themes unless the user explicitly wants a stronger visual direction.
Treat the theme as a layout decision, not only a color decision: the template now changes margins, body size, line spacing, and heading rhythm with the selected theme.
When the report needs stronger packaging rather than a plain cover, also fill the optional metadata fields such as `\reportversion`, `\reportstatsline`, `\reportstatslineb`, `\reporteditionline`, `\reportfrontispiecepath`, `\reportwatermark`, `\reportbackcoverbannerpath`, `\reportbackcoverdisclaimer`, and `\reportbackcovercopyright`.
When the report needs a house style rather than a built-in theme, use `\reportthemeoverridepath` or `\reportthemeoverrides` to override palette, layout, typography, or chrome after the base theme is applied.
Read [references/theme-selection.md](references/theme-selection.md) when you need fast theme selection guidance instead of guessing from theme names alone.

Fill the metadata block first, then write the body around evidence. The report should usually contain:

- title page
- executive summary
- source and method overview
- main analysis sections
- comparisons or tables where useful
- a conclusion section
- an appendix with source inventory, detailed notes, or extra figures when needed

## Writing Rules

1. Write for transfer, not just for chat.
   The PDF should stand on its own for a reader who never saw the original conversation.

2. Organize with `\section{...}` and `\subsection{...}`.
   Reconstruct the clearest research narrative instead of mirroring discovery order.

3. Use images, tables, and diagrams whenever they materially improve understanding.
   Good candidates include source screenshots, timeline comparisons, architecture diagrams, flowcharts, annotated crops, benchmark plots, and before/after contrasts.

4. When a mathematical relationship matters:
   show it in display math using `$$...$$`
   then immediately follow with a flat list explaining every symbol

5. When code or CLI fragments matter:
   wrap them in `lstlisting`
   include a descriptive `caption`
   if the chosen theme uses a border-style code treatment, do not manually add extra boxes around the listing

6. For LaTeX tables, default to the template's `ltablex`-backed `tabularx` base.
   Use fixed-width `L{...}` or `M{...}` columns only for short identifiers, dates, or tags.
   Use `Y` or `C` columns for long prose cells so width adapts inside `\textwidth`.
   When a table may span pages, use the repeated-header pattern with `\endfirsthead` and `\endhead` instead of falling back to rigid all-`p{...}` layouts.
   For source inventories, prefer `L{1.6cm}L{1.8cm}YY` together with the template's `\tablethemeon`, `\tablethemeoff`, and `\sourceledgerheader` helpers.
   Do not wrap the `ltablex` table in a custom environment; use the helper commands immediately around the raw `tabularx` block.

7. Add clickable links in two places when appropriate:
   inline where the reader benefits immediately
   and in an appendix or source table for auditability

8. Use high-signal callout boxes deliberately:
   `findingbox` for the strongest takeaways
   `evidencebox` for source-backed support, methodology, or triangulation notes
   `riskbox` for uncertainty, counterevidence, or failure modes
   `methodbox` for scope assumptions, evaluation setup, or reproducibility notes

9. Keep figures outside callout boxes unless the box is the figure's core explanatory container and layout still remains clean.

10. Do not emit `[citation needed]`, `[TODO]`, or placeholder links in the final LaTeX.

11. End the document with a final top-level section such as `\section{结论与后续问题}`.
    That section should separate:
    - what is well supported
    - what is likely but not fully proven
    - what remains unknown or worth validating next

## Multimodal Evidence Rules

### Images

- Prefer the highest-quality original image that is legally and practically available.
- Crop or annotate only when it improves interpretation.
- State whether the figure is original, extracted, cropped, OCR-assisted, or redrawn.

### Videos

- Probe metadata and subtitle availability before extracting frames.
- Bias toward recall before precision when searching for frames.
- When a slide or animation builds progressively, keep checking until the most complete readable state appears.
- Record a concrete time interval for every figure derived from a video frame or crop.

### PDFs and Papers

- Preserve formulas, tables, figure captions, and page-local context.
- Do not treat OCR text dumps as sufficient when layout carries meaning.

### Code, Data, and Repos

- Record repository URL, branch, commit hash, dataset version, or release tag whenever available.
- Distinguish measured results from source-reported results.

## Provenance And Citation Rules

Every nontrivial figure, table, or strong claim should remain traceable.

- For webpages and PDFs, keep the URL or stable identifier.
- For local files, keep the path and filename.
- For videos, keep the platform URL plus the time interval.
- For derived visuals, state whether the figure is reproduced, redrawn, or synthesized from several sources.
- When several sources support one conclusion, cite the best primary source first and then the strongest corroborating source.

If a source is weak, outdated, or contradictory, say so instead of smoothing it over.

## Plotting And Figure Quality Rules

When a report includes self-drawn charts, treat figure quality as a first-class deliverable, not a cosmetic afterthought.

### Readability Baseline

- Prefer chart types that match the question. Use bars for category comparisons, lines for trends, scatter or bubble for relationships, and avoid pie or donut charts for dense categories.
- Keep label density under control. If labels overlap, split into multiple figures or abbreviate labels and move full names into a nearby table.
- Use explicit value labels only for key points; avoid turning every chart into text clutter.
- Keep axis names, units, and legend semantics explicit and consistent with table terminology.

### Chinese Font And Locale Safety

- If the report is Chinese, all self-drawn charts must support Chinese text in titles, axes, legends, and annotations.
- Set a CJK-capable fallback chain in plotting code and verify actual runtime availability before final rendering.
- Do not assume one specific font exists on every machine. Use ordered fallbacks and fail safe.
- When a plotting library still renders missing glyph boxes, regenerate with a verified available CJK font before compiling the final PDF.

### Visual Style And Export Defaults

- Prefer calm, high-contrast palettes over flashy gradients. Color should encode meaning first.
- Keep grid lines subtle and avoid heavy chart junk.
- Prefer wide layouts for ranking charts so labels remain legible after LaTeX scaling.
- Export figures at print-safe quality: normally `dpi >= 300`, and ensure enough pixel width for full-page usage.
- Preserve consistent style across figures in one report: font family, title hierarchy, spacing, and color logic.

### Chart-Specific QA

- For bubble and scatter charts, explicitly check overlap, marker-size scaling, and annotation collisions.
- For boxplots and violin plots, verify ordering logic and median or quantile labels are readable.
- For log-scale charts, clearly mark the scale in axis labels and ensure tick labels are interpretable.
- For category coverage or ranking charts, ensure sorting logic matches the narrative claim in text.

### PDF-Level Visual Validation

- Do not stop at checking raw PNG files. Validate every figure inside the compiled PDF.
- Check page-level readability on the rendered PDF: tiny text, clipping, overlap, crowded legends, caption collisions, and whitespace balance.
- If the user says charts are unclear or unattractive, redraw and replace figures instead of only adjusting surrounding prose.
- Keep plotting scripts or commands reproducible so figures can be regenerated consistently in later revisions.

## Validation

Before delivery:

- compile the `.tex` successfully
- check that hyperlinks render correctly
- verify that every figure path resolves
- verify that formulas and tables are legible
- visually inspect every self-drawn or derived figure in the rendered PDF for overflow, clipping, overlap, tiny labels, caption collisions, and page-fit problems
- visually inspect every table in the rendered PDF for reasonable column widths, row heights, header wrapping, cell overflow, and overall readability
- if any figure or table looks cramped, overlapping, clipped, or visually unbalanced, revise the LaTeX and rebuild instead of only noting the issue
- remove unsupported claims and broken references
- visually inspect the rendered PDF for spacing, clipping, and caption issues

## Delivery

Deliver all artifacts the task calls for. The default bundle is:

- final `.tex`
- rendered PDF
- downloaded or generated figure assets used by the report
- optional appendix assets such as source tables, OCR output, or subtitle files when they matter to reproducibility

By default, write this bundle under `/home/fanghaotian/Desktop/src/deepresearch/YYYY/MM/DD/<topic-slug>-YYYY-MM-DD/` rather than ad hoc directories elsewhere.

## Bundled Resources

- `assets/report-template.tex`: default LaTeX template for a research-grade multimodal report
- `references/multimodal-ingestion.md`: modality-specific acquisition and provenance checklist
