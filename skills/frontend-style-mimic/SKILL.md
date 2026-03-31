---
name: frontend-style-mimic
description: Extract, document, compare, and reuse the frontend style of an existing web app or frontend repo. Use when the user wants to read a frontend codebase, distill its visual and implementation style into a reusable style pack, then apply or enforce that style in new pages, components, or products.
---

# Frontend Style Mimic

Turn a frontend codebase's style into a reusable style pack, then use that pack as the primary source of truth for later implementation.

## Use This Skill When

- The user wants to study a frontend repo and summarize its style.
- The user wants a reusable style document for a product or codebase.
- The user wants new pages or components to match an existing frontend style.
- The user wants a style-fit review between existing code and a target style.
- The user wants to maintain multiple named frontend styles over time.

## Core Rules

1. Prefer code evidence over visual guesswork. Screenshots help, but tokens, primitives, layout shells, and motion rules must come from source files when available.
2. Separate style into layers. Do not collapse everything into "looks clean" or "looks modern."
3. Record both visual language and implementation language. A style is not only colors and spacing; it also includes component composition, state patterns, and interaction tone.
4. Reuse an existing style pack before re-reading the source repo. Re-open source files only when the pack is missing, stale, or ambiguous.
5. Mark uncertainty explicitly. Distinguish observed facts from reasonable inference.

## Standard Scope

This skill is currently scaffolded for the "standard" tier:

- style extraction
- style application
- style-fit review
- style fork and variant management
- evidence-backed documentation
- anti-pattern and checklist-driven validation

## Style Pack Layout

Every style lives under:

`references/styles/<style-id>/`

Create a new pack with:

`python scripts/style_pack.py init --style-id <style-id> --title "<Title>"`

Each style pack contains:

- `summary.md` - high-level identity, preserved traits, and reuse guidance
- `evidence.md` - source anchors and extraction notes
- `tokens.md` - palette, typography, spacing, radius, shadows, breakpoints
- `components.md` - primitive and composite component patterns
- `layout.md` - shells, grids, density, responsive behavior
- `motion.md` - easing, spring values, reveal patterns, interaction tempo
- `implementation.md` - stack, libraries, structure, authoring conventions
- `anti-patterns.md` - what breaks the style
- `checklist.md` - delivery checklist when applying the style
- `examples.md` - compact, reusable code or structure motifs

Read `references/style-pack-schema.md` before creating or editing a style pack.

## Operation Modes

### 1. Extract Style From A Repo

Read `references/operation-modes.md` and `references/style-review-checklist.md`.

Default extraction order:

1. `package.json` and app entry points
2. global CSS, theme providers, design token files
3. base `ui/` primitives and shared layout wrappers
4. navigation, shells, and one or two representative screens
5. motion helpers, chart wrappers, icon helpers, and notable utilities

Required output:

- a populated style pack
- a short human-readable overview derived from `summary.md`
- explicit unknowns and low-confidence areas

### 2. Apply An Existing Style

Read only the pack files needed for the task:

- Always start with `summary.md`
- Add `tokens.md`, `components.md`, `layout.md`, and `motion.md` as needed
- Read `implementation.md` when making code changes
- Finish with `anti-patterns.md` and `checklist.md`

When implementing:

1. Translate the user request into style constraints.
2. Match the target repo's actual stack rather than force-copying foreign abstractions blindly.
3. Preserve the style's interaction tone, density, and composition patterns.
4. Run a style-fit self-review before delivery.

### 3. Compare Or Review Style Fit

Use this mode when the user wants a review, diff, or compliance check.

Compare candidate code against the style pack across these axes:

- tokens
- surfaces and component primitives
- layout and density
- motion and feedback
- implementation conventions

Report concrete mismatches with file references and severity, not vague adjectives.

### 4. Fork Or Evolve A Style

Use this mode when a new product should inherit an old style with controlled drift.

Workflow:

1. Duplicate the closest parent pack into a new `style-id`.
2. State what is inherited and what is intentionally changed.
3. Keep delta notes in the child pack's `summary.md`.
4. Avoid mutating the parent pack unless the parent style itself changed.

## What To Read

- `references/style-pack-schema.md`
  Use when creating or editing a style pack.
- `references/operation-modes.md`
  Use when you need the detailed step-by-step workflow for extract, apply, review, or fork operations.
- `references/style-review-checklist.md`
  Use before delivery to validate completeness and style fit.

## Scripts

- `python scripts/style_pack.py list`
  List known style packs.
- `python scripts/style_pack.py init --style-id octopus --title "Octopus"`
  Initialize a new style pack from the bundled template.
- `python scripts/style_pack.py lint --style-id octopus`
  Check whether a style pack is structurally complete and whether placeholders remain.
- `python scripts/style_pack.py fork --from-style octopus --to-style octopus-compact --title "Octopus Compact"`
  Create a derived style pack from an existing parent pack.

## Output Expectations

For extraction tasks:

- summarize the style in plain language
- keep the durable details in the style pack
- note what was observed vs inferred

For implementation tasks:

- explain the mapping from request to style rules
- make the code match the pack
- state any unavoidable deviations

For review tasks:

- findings first
- file references
- grouped by severity or impact
