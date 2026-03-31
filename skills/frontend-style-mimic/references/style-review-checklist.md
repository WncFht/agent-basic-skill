# Style Review Checklist

Use this file before delivery, regardless of mode.

## For Extraction

- Did you inspect the frontend stack before naming the style?
- Did you read token and theme entry points?
- Did you inspect primitive components instead of only feature modules?
- Did you inspect at least one layout shell and one representative screen?
- Did you capture motion behavior if the repo has custom transitions?
- Did you distinguish observed facts from inference?
- Did you record source anchors in `evidence.md`?

## For Style Pack Quality

- Is `summary.md` readable by a human without digging through the repo?
- Does `tokens.md` contain actual token names or values when available?
- Does `components.md` explain composition, not just list components?
- Does `layout.md` explain density and responsiveness?
- Does `motion.md` explain timing or transition character?
- Does `implementation.md` explain how the style is encoded in code?
- Does `anti-patterns.md` make future misuse harder?
- Does `checklist.md` help a later implementation task?

## For Application

- Did you read the existing pack before re-reading the source repo?
- Are the new components aligned with the pack's primitive layer?
- Do spacing, radius, shadow, and surface rules match the pack?
- Does the page shell and responsive behavior match the pack?
- Does motion feel consistent instead of generic?
- Did you avoid introducing foreign visual patterns?

## For Review Tasks

- Are findings concrete and evidence-backed?
- Are findings ordered by severity or impact?
- Do findings explain how to fix the mismatch?
- Did you avoid vague style language without code evidence?

