---
name: better-frontend
description: Use for frontend cleanup, dashboards, app screens, or presentation review. Remove TODOs/placeholders/dev reasoning with small diffs; preserve UI language; avoid decorative rewrites.
---

# Better Frontend

## Scope

Use this skill for user-visible UI work: pages, dashboards, admin/workbench surfaces, app screens, landing pages, and frontend copy.

Goal: make the visible product usable and production-ready without turning small cleanup into a redesign.

## Hard Constraints

- Never expose developer notes, TODOs, placeholder explanations, mock/demo labels, implementation plans, design commentary, or reasoning in user-visible UI.
- Preserve the current visible language and product shape unless the user explicitly asks to translate or redesign.
- For an existing page, inspect the current structure and line count before editing. Default to a local diff; do not replace the whole file for copy/demo cleanup.
- For cleanup/productization of a small existing page, keep the result within `max(original_lines + 80, original_lines * 2)` unless the user explicitly asks for a redesign. If that limit is insufficient, explain why before broadening scope.
- Do not use web search for local UI cleanup unless the user asks for external competitors, assets, or current information.
- Dashboard/admin/ops surfaces should be restrained, dense, and scannable; do not use marketing heroes, decorative gradients, glass blur, glow, or large-radius styling as the default way to look polished.
- Cards and panels default to `border-radius <= 8px` unless the project design system already uses larger radii.
- If the project has `.trellis/spec/frontend/`, treat it as the primary frontend rule source; references here are fallback guidance.

## Default Working Rules

1. Identify the visible UI and the exact request type: cleanup, polish, redesign, or new build.
2. For existing pages, record `wc -l` and make the smallest patch that can satisfy the request.
3. Clean visible copy: remove TODO/FIXME/NOTE, placeholder/mock/demo language, future-backend text, sample disclaimers, and developer-facing explanations.
4. Productize within the current layout first: labels, statuses, actions, spacing, borders, and only the structure needed for the user task.
5. Before final, run narrow checks:
   - `wc -l <file>` and compare against the cleanup line-count budget.
   - `rg -n 'TODO|FIXME|NOTE:|placeholder|mock|demo|sample|future backend|developer|reasoning' <file>`.
   - For HTML, strip tags and scan visible text when class names cause false positives.
   - For dashboard/admin pages, scan CSS for `radial-gradient`, `backdrop-filter`, `filter: blur`, heavy `box-shadow`, or `border-radius` above `8px`.
6. Final report should state the result, checks run, and residual risk only; do not add a generic optional follow-up after a narrow cleanup.

## Read References When Needed

- Read `references/banned-content.md` for content that must not appear in visible UI.
- Read `references/production-defaults.md` for default production-readiness standards.
- Read `references/visual-rules.md` for visual output constraints.
- Read `references/page-rules-dashboard.md` for dashboard, admin, and workbench pages.
- Read `references/page-rules-landing.md` for landing pages and brand/product pages.
- Read `references/pre-delivery-checklist.md` before final delivery.

## Red Flags

Stop and revise if any of these appear:

- Visible TODO, NOTE, placeholder explanation, mock/demo label, design note, or implementation plan.
- Visible copy explains the UI to a developer instead of helping the end user act.
- A small cleanup expands into a template rewrite or exceeds the line-count budget without explicit user approval.
- The visible UI language changes without user request.
- Dashboard/admin/ops pages gain a hero, decorative chart, decorative KPI row, right rail, gradient/glass/glow treatment, or many rounded pills just to look busy.
