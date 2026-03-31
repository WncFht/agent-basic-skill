# Layout Patterns For Business And Data-Heavy Decks

Use slide intent to choose the Slidev implementation strategy.

## Intent -> Pattern Mapping

### Cover

- Use `layout: cover` or `layout: intro`
- Large title, subtitle, optional hook metric

### Agenda Or Roadmap

- Use `layout: default`
- Prefer 3-6 sections
- Use `<Toc />` when that is sufficient

### Section Divider

- Use `layout: section`
- Keep it sparse

### Thesis Or Statement

- Use `layout: statement`
- One claim, one supporting line

### KPI Or Hero Metric

- Use `layout: fact` for a simple single-metric page
- Use a custom component or card grid for multiple KPIs

### Comparison

- Use `layout: two-cols` or `two-cols-header`
- Keep each column internally consistent

### Process Or Sequence

- Use normal markdown with `VClicks`, or a diagram if the process is structural
- Avoid giant bullet dumps

### Chart Or Trend

- Use a custom component, Mermaid, embedded SVG, or image
- Keep one chart per slide unless comparison is the point

### Card Grid / Bento Summary

- Prefer `layout: none` or `full` plus custom HTML, MDC, or a local Vue component
- Best for summary dashboards, financial takeaways, risk lists, or product feature overviews

### Quote

- Use `layout: quote`

### Appendix

- Use `layout: default`
- Keep references, backup analysis, or low-priority evidence here

## Practical Rule

Built-in layouts are enough for simple slides. For repeated visual structures, make a local component under `components/`.

## Minimal Bento Example

```md
---
layout: none
class: px-10 py-8
---

# 经营亮点

<div class="bento-grid">
  <div class="card card-hero">
    <div class="eyebrow">Revenue</div>
    <div class="metric">32%</div>
    <div class="support">同比增长，主要受高端产品带动</div>
  </div>
  <div class="card">
    <div class="eyebrow">Margin</div>
    <div class="metric">18.4%</div>
    <div class="support">盈利能力继续改善</div>
  </div>
  <div class="card">
    <div class="eyebrow">Risk</div>
    <div class="metric">渠道</div>
    <div class="support">库存与区域波动仍需关注</div>
  </div>
</div>

<style scoped>
.bento-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 1rem;
  margin-top: 1.5rem;
}
.card {
  border-radius: 24px;
  padding: 1.25rem;
  background: #111827;
  color: #f9fafb;
}
.card-hero {
  min-height: 260px;
}
.eyebrow {
  font-size: 0.8rem;
  opacity: 0.7;
}
.metric {
  font-size: 3rem;
  font-weight: 700;
  margin-top: 0.5rem;
}
.support {
  margin-top: 0.75rem;
  font-size: 0.95rem;
  line-height: 1.4;
}
</style>
```

When this pattern repeats across several slides, convert it into a component instead of duplicating markup.
