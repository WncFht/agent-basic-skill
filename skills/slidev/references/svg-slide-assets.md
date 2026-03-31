# SVG Slide Assets

Use SVG as an optional visual asset path inside a Slidev workflow.

## When SVG Is Worth It

- hero stat slide
- architecture diagram
- process diagram
- polished title slide background
- reusable editable visual that may also be imported elsewhere

## Rules

1. Use `viewBox="0 0 1280 720"` unless a different canvas is clearly needed.
2. Keep text as real text when editability matters.
3. Group related elements semantically when possible.
4. Avoid unnecessary rasterization.
5. Save assets under `public/svg/`.

## Integration Patterns

### As an image asset

```md
---
layout: full
---

<img src="/svg/hero-overview.svg" class="w-full h-full object-contain" />
```

### As part of a normal slide

```md
---
layout: two-cols
---

# 左侧说明

::right::

![](/svg/system-architecture.svg){width=520px}
```

### Inline SVG

Use only when the slide needs direct styling or animation control.

## Deck Strategy

If the user asks for both a Slidev deck and editable single-slide assets:

- keep the canonical content in Slidev
- generate matching SVG for the hero or diagram-heavy slides
- store both in the same deck workspace

## Practical Rule

Do not force every slide through SVG. Use it where editability or precise art direction makes it worth the extra complexity.
