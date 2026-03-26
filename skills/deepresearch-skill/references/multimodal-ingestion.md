# Multimodal Ingestion Reference

Read this file when the task includes multiple source types or when the final report needs strong provenance.

## Source Ledger Schema

Track at least these fields for every source:

- `source_id`
- `modality`
- `title`
- `author_or_org`
- `url_or_path`
- `published_at`
- `accessed_at`
- `credibility_class`
- `research_role`
- `notes`

Recommended credibility classes:

- `primary`: official docs, original papers, direct measurements, first-party repos, raw filings, original media
- `secondary`: reputable summaries, reviews, analysis pieces
- `illustrative`: screenshots, examples, forum posts, marketing pages, commentary

## Web And Text Sources

- Prefer primary and current sources when the topic is time-sensitive.
- Preserve the canonical URL, page title, and access date.
- Extract only the passages that matter to the argument.
- Separate direct facts from your interpretation.

For high-stakes or recent claims, compare at least two sources unless the canonical primary source is sufficient on its own.

## PDFs, Papers, And Reports

- Preserve page numbers, figure numbers, and nearby captions.
- Use layout-aware parsing when formulas, tables, or figure references matter.
- Keep the original PDF filename and stable source link.
- When quoting or paraphrasing experimental results, record the exact page or table number in your notes.

If a PDF is scanned or visually dense, use OCR or a visual parser, then verify against rendered pages before citing details.

## Images

- Record the original path or URL plus image filename.
- Note whether the image is native, compressed, cropped, stitched, annotated, or OCR-assisted.
- When extracting information from charts or screenshots, say whether the result is read directly, estimated visually, or transcribed with OCR.

If the image is low resolution:

- look for a higher-resolution original first
- then crop or enlarge only the relevant region
- avoid over-interpreting unreadable details

## Video And Audio

- Record platform, URL, title, channel or author, duration, and publication date.
- Prefer manual subtitles over automatic ones.
- Use subtitle spans to locate candidate frames or key discussion windows.
- Generate a dense candidate set before choosing a final frame.
- Preserve time intervals, not just a single timestamp, for frame provenance.

For progressive slides, demos, or whiteboard builds:

- inspect several nearby frames
- prefer the most complete readable state
- keep intermediate states only if they teach a distinct step

If audio is transcribed:

- retain the timestamped transcript or subtitle file
- note the transcription method if accuracy could matter

## Code, Repos, And Structured Data

- Record repository URL, branch, commit hash, release tag, or package version.
- Record dataset origin, schema version, and extraction date.
- Distinguish between reproduced results and source-reported results.
- When you compute a metric yourself, state the computation method and inputs.

## Claim Mapping

For each major report claim, keep a private working map:

- `claim`
- `supporting_sources`
- `source_type`
- `direct_or_inferred`
- `confidence`
- `open_risks`

Use this map to decide which claims deserve callout boxes, tables, or explicit caveats.

## Figure Provenance Checklist

For every report figure, know:

- what file is being included
- whether it is original, extracted, cropped, stitched, redrawn, or synthesized
- the exact source URL or path
- the time interval if it came from a video
- whether any OCR, annotation, or redrawing was applied

Good caption pattern:

`图 X：结论性描述。来源：某论文图 3 / 某网页截图 / 某视频 00:12:31--00:12:46 / 作者自绘。`

## Appendix Suggestions

Include an appendix when the report benefits from auditability. Common appendix blocks:

- source ledger table
- dataset or benchmark definitions
- method notes and assumptions
- extra figures that would clutter the main narrative
- transcript snippets or OCR excerpts used to interpret a key image or frame
