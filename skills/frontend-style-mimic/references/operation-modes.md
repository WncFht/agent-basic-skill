# Operation Modes

This file expands the four core modes in `SKILL.md`.

## Mode 1: Extract Style

Use when the source of truth is a frontend repo or a live frontend plus code access.

### Step 1: Bound The Scope

Identify:

- frontend root
- framework and styling stack
- theme and token entry points
- base component layer
- representative screens

Do not start by reading the whole repo. Read the highest-signal files first.

### Step 2: Build An Evidence Ledger

Start `evidence.md` early.

Capture:

- which files define tokens
- which files define primitive components
- which files demonstrate layout shells
- which files demonstrate motion or feedback
- which files demonstrate responsive behavior

### Step 3: Fill The Style Pack By Layer

Recommended order:

1. `summary.md`
2. `tokens.md`
3. `components.md`
4. `layout.md`
5. `motion.md`
6. `implementation.md`
7. `anti-patterns.md`
8. `checklist.md`
9. `examples.md`

### Step 4: Validate The Pack

Ask:

- Is every major style claim backed by evidence?
- Are the distinctive traits actually distinctive, not generic?
- Does the pack cover both visual and implementation language?
- Could another agent build a matching page from this pack?

### Step 5: Deliver

Deliver:

- a short narrative summary
- the populated style pack
- unknowns and next extraction targets if coverage is incomplete

## Mode 2: Apply Style

Use when the style pack already exists and the user wants new code that matches it.

### Step 1: Read Only What You Need

Always:

- `summary.md`

Usually:

- `tokens.md`
- `components.md`
- `layout.md`
- `motion.md`

When coding:

- `implementation.md`
- `anti-patterns.md`
- `checklist.md`

### Step 2: Map The Task To Style Constraints

For each requested page or component, define:

- visual constraints
- composition constraints
- responsive constraints
- interaction constraints
- implementation constraints

### Step 3: Implement In The Target Stack

Do not blindly transplant abstractions from another repo when the current repo uses different primitives. Preserve the style intent while respecting the local codebase.

### Step 4: Self-Audit

Use `checklist.md` and `anti-patterns.md`.

If a deviation is necessary, state it explicitly.

## Mode 3: Review Style Fit

Use when the user asks whether a page, component, or repo matches the target style.

### Review Axes

- Token fidelity
- Surface treatment
- Layout rhythm and density
- Motion and interaction tone
- Implementation conventions

### Output Shape

Prefer findings like:

- what mismatches
- why it mismatches
- where it happens
- how to fix it

## Mode 4: Fork Or Evolve A Style

Use when the user wants a derivative style.

### Workflow

1. Copy the closest existing pack into a new `style-id`.
2. Add parent lineage in `summary.md`.
3. Record deliberate differences in the child pack.
4. Keep generic inheritance in sync, but avoid accidental drift between parent and child.

Use:

`python scripts/style_pack.py fork --from-style <parent> --to-style <child> --title "<Child Title>"`

## When Not To Use This Skill

- Pure visual ideation without a source style
- Brand strategy without code or frontend artifacts
- One-off CSS tweaks where no reusable style knowledge is needed
