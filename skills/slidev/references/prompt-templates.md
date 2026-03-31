# Prompt Templates

Use these as skeletons when model assistance is helpful. Adapt them to the current deck instead of copying them blindly.

## Outline Architect

Use when building `data/outline.json`.

```text
Role: PPT structure architect

Task: Based on the topic, audience, goal, and research context, produce a structured deck outline.

Requirements:
- one slide, one core job
- logical progression
- each slide must include title, intent, key message, suggested layout, and evidence refs if needed
- output JSON only
```

## Report Analysis

Use before converting a long report into slides.

```text
Analyze the source document as a domain expert.

Produce:
1. executive summary
2. key metrics and comparisons
3. unusual or risky findings
4. recommendations or conclusions
5. a list of slide-worthy insights

Write clearly and preserve factual grounding.
```

## Talk Track Writer

Use when the user wants a lecture script, pitch script, or strong presenter notes.

```text
Turn this outline into a presenter-friendly talk track.

For each slide:
- purpose
- opening line
- 2-4 speaking beats
- transition sentence
- optional timing

Keep visible slide text concise and move explanation into notes.
```

## SVG Slide Generator

Use for hero slides or diagram-heavy visual assets.

```text
Create one polished SVG slide asset with viewBox 0 0 1280 720.

Use a card-based or diagram-based layout as needed.
Preserve strong hierarchy, generous spacing, and editable text.
Return SVG only.
```

## Card Extraction For Dense Documents

Use when summarizing long reports into slide-ready content.

```text
Convert this document summary into slide-ready cards.

Rules:
- one card, one idea
- promote important numbers to hero values
- keep support text concise
- identify which cards belong together on a single slide
- return a structured JSON plan
```
