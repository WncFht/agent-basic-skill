# Style Pack Schema

This file defines the canonical structure for each style pack under:

`references/styles/<style-id>/`

## Design Principles

1. Keep the pack durable. It should survive after the original task ends.
2. Keep the pack evidence-backed. Major claims should point to source files in `evidence.md`.
3. Keep the pack reusable. It should help later implementation, not only act as a report.
4. Separate observed facts from inference when confidence is limited.

## Required Files

### `summary.md`

Purpose:

- describe the style in human terms
- state what must be preserved
- state what can bend
- record lineage when the style is a fork or variant

Recommended sections:

- Identity
- Lineage
- Keep At All Costs
- Flexible Areas
- Distinctive Traits
- Reuse Guidance
- Source Anchors

### `evidence.md`

Purpose:

- record the source basis for the pack
- keep extraction grounded in concrete files

Recommended sections:

- Scope
- High-signal files
- File-by-file notes
- Open questions

Each note should prefer:

- file path
- why the file matters
- what it proves about the style

### `tokens.md`

Purpose:

- capture the low-level design system tokens

Recommended sections:

- Color system
- Typography
- Radius and border treatment
- Shadow language
- Spacing scale
- Breakpoints and responsive thresholds
- Theme or dark mode behavior

Use concrete token names and values when possible.

### `components.md`

Purpose:

- document the visual and structural rules of core components

Recommended sections:

- Primitive layer
- Buttons and controls
- Cards and surfaces
- Forms and input states
- Navigation
- Data display
- Overlays and dialogs
- Empty, loading, and error states

Record both appearance and composition rules.

### `layout.md`

Purpose:

- explain how pages are assembled

Recommended sections:

- Page shell
- Navigation shell
- Container widths and padding
- Grid, list, and section rhythm
- Content density
- Desktop vs mobile behavior

### `motion.md`

Purpose:

- capture the interaction tempo and transition language

Recommended sections:

- Motion voice
- Timing and easing
- Spring presets
- Enter and exit patterns
- Hover, focus, and feedback
- When motion is intentionally restrained

### `implementation.md`

Purpose:

- record how the style is encoded in code

Recommended sections:

- Framework and libraries
- Token implementation path
- Primitive component strategy
- Utility helpers
- State and data patterns that shape the UI
- File organization and naming conventions
- Known implementation constraints

### `anti-patterns.md`

Purpose:

- define what breaks the style

Recommended sections:

- Visual mismatches
- Composition mismatches
- Motion mismatches
- Implementation mismatches
- Migration hazards

Use short, concrete rules.

### `checklist.md`

Purpose:

- act as the final audit list when applying the style

Recommended sections:

- Before coding
- During implementation
- Pre-delivery
- Known acceptable deviations

### `examples.md`

Purpose:

- preserve short, high-value patterns that are easy to reuse later

Recommended sections:

- Page skeletons
- Card or panel motifs
- Form patterns
- Motion wrapper patterns
- Good snippet references

Keep examples compact. Prefer references or excerpts over long file dumps.

## Variant Lineage

When a style is derived from another style, record this in `summary.md`.

Recommended fields:

- Parent style id
- Inherited traits
- Deliberate changes
- Expected use cases for the variant

## Evidence Standard

Strong style claims should be backed by at least one source anchor in `evidence.md`.

Examples:

- "Uses semantic OKLCH tokens with distinct light and dark palettes"
- "Prefers rounded cards with soft borders and low-elevation shadows"
- "Uses staggered list entry with fast ease-out motion"

## Confidence Labels

Use labels when helpful:

- `Observed` - explicit in source code
- `Inferred` - reasonable conclusion from repeated patterns
- `Open` - not settled yet

## Minimal Read Order

When the pack already exists, read in this order unless the task needs more:

1. `summary.md`
2. `tokens.md`
3. `components.md`
4. `layout.md`
5. `motion.md`
6. `implementation.md`
7. `anti-patterns.md`
8. `checklist.md`
