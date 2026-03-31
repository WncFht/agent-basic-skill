# Deck Quality Checks

Run these checks before delivery.

## Structure

- every slide has a clear job
- the deck has a visible narrative arc
- section boundaries are obvious
- appendix content is separated from core story

## Content Density

- no slide tries to explain two unrelated ideas
- long paragraphs are rare
- charts have enough room to read
- card grids are not overloaded

## Accuracy

- factual claims have checked sources
- time-sensitive claims were researched before writing
- numbers match the cited source

## Speaker Usefulness

- presenter notes exist when the deck is meant to be spoken
- slide order supports natural transitions
- visible text is audience-facing, not transcript-facing

## Visual Consistency

- aspect ratio is correct
- layout choice matches slide intent
- repeated patterns use consistent spacing and styles
- SVG and image assets resolve correctly

## Runtime And Export

- `slidev dev` renders without breakage
- `slidev build` succeeds for HTML delivery
- `slidev export` succeeds for requested formats
- exported output keeps the intended hierarchy and readability

## Practical Rule

Do not deliver the deck just because the markdown is finished. Deliver it only after the runtime and the requested exports are proven.
