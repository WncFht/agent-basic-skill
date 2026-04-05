# Report Validation

Read this file when the report includes many figures, self-drawn charts, visually dense tables, or layout-sensitive evidence.

## Baseline PDF Checks

Before delivery, verify all of the following in the rendered PDF:

- hyperlinks work
- figure paths resolve
- formulas remain legible
- tables have reasonable column widths, row heights, and header wrapping
- no obvious clipping, overlap, or unreadably small text appears on the page

If any figure or table looks cramped, overlapping, clipped, or visually unbalanced, revise and rebuild instead of only noting the defect.

## Provenance Checks

Every nontrivial figure, table, or strong claim should remain traceable.

- For webpages and PDFs, keep the URL or stable identifier.
- For local files, keep the path and filename.
- For videos, keep the platform URL plus the time interval.
- For derived visuals, state whether the figure is reproduced, cropped, OCR-assisted, redrawn, or synthesized from several sources.

## Figure Checks

- Validate figures inside the compiled PDF, not only as standalone PNG files.
- Check page-level readability: tiny labels, clipping, crowded legends, caption collisions, and whitespace balance.
- If the user says a figure is unclear, redraw or replace it instead of only changing nearby prose.

## Table Checks

- Prefer adaptive widths over rigid all-`p{...}` layouts when long prose is present.
- Check for bad line breaks, row blow-up, clipped cells, or headers that become harder to scan after wrapping.
- If a source ledger or comparison table spans pages, confirm the repeated header remains correct and readable.

## Self-Drawn Chart Checks

When the report includes self-drawn charts:

- choose a chart type that matches the question
- keep label density under control
- keep axis names, units, and legend semantics explicit
- prefer calm, high-contrast palettes over decorative gradients
- export at print-safe quality, normally `dpi >= 300`
- preserve consistent typography and color logic across charts in one report

If the report is Chinese, ensure the chart rendering stack can display Chinese text correctly before final export.
