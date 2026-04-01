# Theme Selection

Use this note when a report should look intentional but the user did not specify a theme.

## Default Picks

- `warm-academic`: best default for Chinese research reports, due diligence notes, and balanced long-form reading.
- `paper-classic`: safest print-first option when the deliverable should feel formal and conservative.
- `github-light`: good for engineering docs, repo audits, tool comparisons, and README-like reports.
- `nord-frost`: use for modern technical reports when a cooler and slightly more productized tone fits.

## Stronger Editorial Looks

- `classic-thesis`: use for academic or archival reports that should feel thesis-like and centered.
- `elegant-book`: use for polished narrative reports with a more bookish rhythm and generous spacing.
- `tufte`: use when wide margins and sparse, essay-like presentation help readability.
- `ink-wash`: use when the report should feel restrained, minimalist, and highly text-led.

## Specialized Looks

- `ieee-journal`: use for paper-like technical briefs, benchmark summaries, and dense evidence-heavy documents.
- `ocean-breeze`: use for lighter product or market reports that still need a clean technical feel.
- `chinese-red`: use sparingly for branded Chinese reports, celebratory editions, or strongly thematic packaging.
- `solarized-light`: use for long reading sessions when softer contrast is helpful.

## Practical Rules

- Prefer lighter print-safe themes unless the user explicitly wants a stylized artifact.
- If the report includes many code blocks, `nord-frost`, `tufte`, and `ieee-journal` work well because the template switches them to a border-led code style.
- If the report needs stronger packaging, pair the chosen theme with `\reportversion`, `\reportstatsline`, `\reportfrontispiecepath`, and back-cover metadata instead of overloading the body with decorative elements.
- If none of the built-ins fit, start from the closest theme and override it with `\reportthemeoverridepath` or `\reportthemeoverrides`.
