# Frontend Slides Memory

Versioned lessons learned for `frontend-slides`.

Read this file before generating or modifying any presentation. Add only reusable, verified rules. Do not store one-off narratives here.

## Current Rules

- Build large single-file HTML decks into a temporary output first. Replace the final delivery file only after sanity checks pass.
- Treat scrollability as a first-class requirement for slide navigation. Multi-slide decks must have a real scroll container before nav-dot, keyboard, wheel, or touch logic can work.
- Keep searches and extraction scoped to the target presentation file or task directory. Broad searches can contaminate the output with logs or unrelated artifacts.
- For enhancement work, prefer small, local edits over large copy-paste rewrites. Re-check viewport fitting after every layout-affecting change.
- When browser automation cannot load `file://`, serve the deck over a local HTTP server for verification.

## Failure Patterns

- `html, body { height: 100%; }` can collapse document scrolling for stacked full-screen slides. Symptom: `scrollTo()` runs but `window.scrollY` stays near zero, and all navigation appears broken.
- Large HTML outputs can be silently corrupted by copied logs or overly broad search results. Symptom: file size becomes implausibly large, `<!DOCTYPE html>` is not at byte 0, or the file no longer ends cleanly with `</html>`.
- Apparent navigation-state bugs are often layout bugs first. Check file integrity and scroll metrics before debugging wheel locks, active-slide state, or smooth-scroll timing.

## Verification Checklist

- File integrity:
  - `<!DOCTYPE html>` starts at byte 0.
  - File ends with `</html>`.
  - File size is plausible for the deck content.
- Scrollability:
  - For multi-slide decks, `document.documentElement.scrollHeight > window.innerHeight`.
  - `window.scrollTo({ top: target.offsetTop })` changes `window.scrollY` after settle time.
- Navigation:
  - Nav-dot click reaches the intended slide.
  - `ArrowDown` / `ArrowUp` move one slide at a time.
  - Wheel navigation moves one slide at a time after settle time.
  - Active nav state matches the visible slide after scrolling settles.
- Presentation quality:
  - No self-generated console errors.
  - Slides fit at 1280x720 without internal slide scrolling.

## Update Protocol

- Update this file when a task reveals a reusable failure mode, a reusable prevention rule, or a reusable verification step.
- Each new item must be concrete, short, and action-oriented.
- Prefer rules that explain both symptom and prevention.
- Delete or rewrite entries that become obsolete.
