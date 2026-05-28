# Frontend Boundaries

Keep pages focused on presentation, interaction, and local state.

## Page Rules

- One page should have one main job.
- Split areas that have different business rhythms, state, or test needs.
- Move complex data shaping, permissions, persistence, and domain decisions out of the page layer.
- Keep reusable UI pieces independent enough to understand and test.

## Split Signals

- The page mixes multiple unrelated workflows.
- Data loading, filtering, submit logic, feedback, and permissions are tangled with markup.
- A local section already has its own state, actions, and failure modes.

## Avoid

- giant page files
- backend response shapes leaking directly into every component
- page-level code deciding complex business rules
- view code becoming the only place where behavior is understood
