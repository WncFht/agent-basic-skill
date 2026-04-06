# Template Usage

Read this file when you need template-specific guidance rather than core research workflow guidance.

## Metadata Block

Fill the metadata block before writing the body.

Core fields:

- `\reporttheme`
- `\reporttitle`
- `\reportsubtitle`
- `\reportauthors`
- `\reportdate`
- `\researchquestion`
- `\reportscope`
- `\reportaudience`
- `\sourcewindow`

Optional packaging fields:

- `\reportversion`
- `\reportstatsline`
- `\reportstatslineb`
- `\reporteditionline`
- `\reportfrontispiecepath`
- `\reportwatermark`
- `\reportbackcoverbannerpath`
- `\reportbackcoverdisclaimer`
- `\reportbackcovercopyright`

Use the optional packaging fields only when the report benefits from stronger delivery packaging. Do not add them mechanically to every report.

If the report needs a house style rather than a built-in theme, use:

- `\reportthemeoverridepath`
- `\reportthemeoverrides`

## Structure

The template works best when the body stays evidence-first.

A good default order is:

- title page
- executive summary
- scope and method
- main analysis
- contradictions, risks, or uncertainty
- conclusion and next questions
- appendix or source ledger when auditability matters

## Tables

Default to the template's `ltablex`-backed `tabularx` base.

- Use `L{...}` or `M{...}` only for short identifiers, dates, or tags.
- Use `Y` or `C` for long prose cells so width adapts inside `\textwidth`.
- When a table may span pages, use the repeated-header pattern with `\endfirsthead` and `\endhead`.
- For source inventories, prefer `L{1.6cm}L{1.8cm}YY` together with `\tablethemeon`, `\tablethemeoff`, and `\sourceledgerheader`.
- Do not wrap the `ltablex` table in a custom environment; place the helper commands immediately around the raw `tabularx` block.

## Code Listings

When code or CLI fragments matter:

- wrap them in `lstlisting`
- include a descriptive `caption`
- keep snippets focused on the point being made

If the chosen theme uses a border-style code treatment, do not manually add extra boxes around the listing.

## Callout Boxes

Use callouts deliberately:

- `findingbox` for the strongest takeaways
- `evidencebox` for source-backed support or triangulation notes
- `riskbox` for uncertainty, counterevidence, or failure modes
- `methodbox` for scope assumptions, evaluation setup, or reproducibility notes

Keep figures outside callout boxes unless the box itself is the clearest explanatory container and the layout still remains clean.
