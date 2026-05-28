# Banned Content In Visible UI

Visible UI must serve the end user, not the developer, reviewer, or design process.

## Ban

- `TODO`, `FIXME`, `NOTE:`
- `mock`, `placeholder`, "sample", "demo"
- "connect backend later"
- "replace with real data"
- "this section demonstrates..."
- "this component shows..."
- "temporary implementation"
- explanations of design decisions or implementation choices
- copy that describes the UI material itself, such as glass, glow, refraction, blur, floating layers, shimmer, or gradient richness

## Rule

If the sentence explains how the interface was built, why it looks good, or what it is demonstrating, keep it out of the visible product surface.

## Allowed Direction

Replace developer/design commentary with user-facing state, outcome, risk, or action.

Examples:

- Instead of visual-material commentary, show weather, finance, workflow, or domain state.
- Instead of "mock data", either wire real data, label a real empty state, or keep the note in code/docs rather than UI.
