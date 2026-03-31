# Speaker Notes And Talk Track

Treat narration as part of the deck, not an afterthought.

## Two Layers

### Presenter Notes

Keep concise notes inside each slide as HTML comments.

Good per-slide notes usually contain:

- slide purpose
- opening line
- 2-4 speaking beats
- transition out
- optional timing cue

Example:

```md
<!--
Purpose: Explain why the market changed this year.
Open: "Before looking at revenue, we need to understand the demand reset."
Beats:
1. Demand slowed in Q2.
2. Premium segment recovered first.
3. This explains the mix shift on the next slide.
Transition: "With that context, the revenue split becomes easier to read."
Time: 45s
-->
```

### Full Talk Track

Use `notes/talk-track.md` when the user wants:

- a full演讲稿
- a lecture script
- a pitch rehearsal script
- a deliverable separate from the deck itself

## Conversion Rules

### If the user gives a manuscript

- keep the manuscript's argument flow
- compress repeated phrasing
- map each speaking beat to one slide
- do not force every paragraph into visible slide text

### If the user gives only a topic

- write slide notes after the outline and page plan stabilize
- visible slide text should stay concise
- let notes hold the connective tissue and spoken explanation

## Practical Rule

Visible slide content is for the audience.

Presenter notes are for the speaker.

Do not overload slides just because the talk needs more words.
