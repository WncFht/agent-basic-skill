# Topic Study Workflow

Use this workflow when a user wants to deeply read a whole Shuiyuan thread, split it by timeline, or study it together with images.

## Recommended pipeline

1. **Inspect completeness first**
   - Run `scripts/inspect_topic.py <topic>`.
   - Check whether `db_post_count`, `json_page_count`, and `raw_page_count` are complete enough for analysis/export.

2. **If the user wants the whole thread with images, prefer a full sync**
   - Run `scripts/ensure_cached.py <topic> --refresh-mode full`.

3. **Prefer the default export root unless the user explicitly wants a duplicate copy**
   - Run `scripts/export_topic.py <topic>`.
   - Do not pass `--save-dir` just for convenience.

4. **Build timeline buckets before writing notes**
   - Run `scripts/plan_topic_study.py <topic> --granularity week`.
   - Run `scripts/plan_topic_study.py <topic> --granularity month`.

5. **Read representative images directly**
   - Prefer direct visual reading on the returned local image path.
   - If the user explicitly forbids OCR, do not use OCR.

6. **Write notes next to the exported thread**
   - Put study notes beside the exported Markdown.

7. **Normalize note images before final delivery**
   - Run `scripts/postprocess_study_markdown.py <note.md> [more notes...]`.
   - Use `--check` if you only want to verify whether a note still needs rewriting.
