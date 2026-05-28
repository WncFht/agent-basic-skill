# Dashboard / Admin / Workbench Pages

Use for dashboard, admin, console, workspace, workbench, internal tool, and data-heavy operation pages.

## Goal

Make the page efficient, stable, and maintainable. It should support repeated work, not perform like a marketing hero.

## Prefer

- Direct sidebar/content or filter/table/list/detail structures.
- First-screen access to the main operation, state, result, or queue.
- Charts only for real trend, comparison, or distribution questions.
- Cards only for meaningful grouping.
- Functional copy for filters, forms, tables, statuses, and feedback.
- In-place cleanup for existing dashboard files: improve copy, spacing, borders, and labels before adding new regions.

## Avoid

- hero sections in admin pages
- KPI-card rows as the default first response
- charts, progress rings, or trend arrows without real data purpose
- command-center or cockpit language for ordinary workflows
- decorative right rails added only to make the page look busy
- repeated oversized rounded cards and pills across every surface
- rewriting a small existing page into a large dashboard template when the user mainly asked to remove demo/placeholder leakage

## Check

The user should quickly see what they can do, where to click, and what state needs attention.

For cleanup of an existing page, compare the final line count with the original. If it exceeds `max(original_lines + 80, original_lines * 2)`, treat that as a redesign and require explicit user intent or a clear explanation.
