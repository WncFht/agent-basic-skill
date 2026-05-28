# Visual Rules

Make the surface feel like a maintained product, not a generated showcase.

## Priorities

1. Clear task path.
2. Stable layout.
3. Useful information hierarchy.
4. Consistent spacing, radius, borders, and shadows.
5. Visual style that supports the domain.

## Prefer

- Existing design language when present.
- Conservative layout for admin, dashboard, and operational tools.
- Components that expose real user action or real information.
- Short product copy with concrete state, result, or action.
- Cards only for genuine grouping, repeated items, or framed tools.
- Small, local changes when improving an existing page that mainly has copy leakage or demo styling.

## Avoid

- marketing-style hero sections inside dashboards
- decorative KPI cards without a task need
- badges, pills, charts, and status dots with no information value
- glassmorphism, neon glow, heavy blur, exaggerated gradients, and large rounded rectangles as default polish
- developer notes, implementation explanations, design commentary, or AI-style placeholder copy
- self-important names such as command center or cockpit for ordinary tools

## Review

Before delivery, ask:

- Does the first screen support the user's main job?
- Is any decoration replacing real structure?
- Would the UI still work after removing decorative copy and nonessential badges/charts?
- Is any visible text written for developers instead of users?
- Did the edit preserve the page's visible language and avoid unnecessary line-count growth?
