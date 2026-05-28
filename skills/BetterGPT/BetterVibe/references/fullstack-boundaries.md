# Fullstack Boundaries

Use this when a change crosses UI, API, domain logic, persistence, or integration layers.

## Default Split

- Frontend: display, interaction, user path, local state.
- Backend: business rules, authorization, consistency, persistence, side effects.
- Boundary/BFF: aggregation, adaptation, protocol shaping when truly needed.

## Coordination Rules

- Do not push backend consistency problems into frontend workarounds.
- Do not make APIs page-specific unless the product contract really is page-specific.
- Do not turn a BFF into a second business layer.
- Keep cross-layer contracts explicit and small.

## Warning Signs

- The same business rule appears in frontend and backend.
- A UI change forces broad API and service rewrites.
- Backend responses are shaped for one screen with many temporary fields.
- A small feature change touches several large files across both sides.
