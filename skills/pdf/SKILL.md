---
name: "pdf"
description: "Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout matter; prefer MinerU API first for parsing/extraction, then use visual checks with Poppler and Python tools such as `reportlab`, `pdfplumber`, and `pypdf` for generation or fallback extraction."
---


# PDF Skill

## When to use
- Read or review PDF content where layout and visuals matter.
- Extract structured content from PDF/doc/docx/ppt/pptx/image/html inputs.
- Create PDFs programmatically with reliable formatting.
- Validate final rendering before delivery.

## Preferred parser order
1. Prefer MinerU API for parsing and structured extraction whenever `MINERU_API_TOKEN` or `MINERU_API_KEY` is available.
   - Public URL input: `POST https://mineru.net/api/v4/extract/task`
   - Local file input: `POST https://mineru.net/api/v4/file-urls/batch`, then upload with `PUT`; MinerU auto-submits the parse task after upload, then poll `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}`
2. Fall back to `pdfplumber` or `pypdf` only when MinerU cannot be used or when a lightweight local check is enough.
3. Keep visual review separate from parsing: render pages to PNG and inspect them when layout fidelity matters.

## Workflow
1. Prefer MinerU first for parsing.
   - Use `model_version: "pipeline"` by default.
   - Use `model_version: "vlm"` for harder scanned or visually complex documents.
   - Use `model_version: "MinerU-HTML"` for HTML inputs.
   - Enable `is_ocr` for scanned PDFs when text is not directly extractable.
   - Keep `enable_formula` and `enable_table` enabled unless the task explicitly favors speed over fidelity.
2. Poll until the task reaches `done` or `failed`.
   - Single-file query: `GET https://mineru.net/api/v4/extract/task/{task_id}`
   - Batch query: `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}`
   - Watch `state`: `waiting-file`, `pending`, `running`, `converting`, `done`, `failed`
3. When MinerU finishes, download `full_zip_url` and inspect the extracted artifacts.
   - Non-HTML inputs: prefer `full.md`; use `content_list.json` or layout/model JSON only when needed.
   - HTML inputs: expect `full.md` and `main.html`.
4. Prefer visual review for layout checks: render PDF pages to PNGs and inspect them.
   - Use `pdftoppm` if available.
   - If unavailable, install Poppler or ask the user to review the output locally.
5. Use `reportlab` to generate PDFs when creating new documents.
6. Use `pdfplumber` (or `pypdf`) for fallback extraction and quick checks; do not rely on it for layout fidelity.
7. After each meaningful update, re-render pages and verify alignment, spacing, and legibility.

## MinerU quick reference
- Before calling MinerU in a raw shell, normalize the auth env once:
```
export MINERU_API_TOKEN="${MINERU_API_TOKEN:-${MINERU_API_KEY:-}}"
```
- Auth header: `Authorization: Bearer $MINERU_API_TOKEN`
- Single public file parse:
```
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
  --header "Authorization: Bearer $MINERU_API_TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'Accept: */*' \
  --data-raw '{
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "pipeline"
  }'
```
- Single task polling:
```
curl --location --request GET "https://mineru.net/api/v4/extract/task/$TASK_ID" \
  --header "Authorization: Bearer $MINERU_API_TOKEN" \
  --header 'Accept: */*'
```
- Local file upload flow:
```
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
  --header "Authorization: Bearer $MINERU_API_TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'Accept: */*' \
  --data-raw '{
    "files": [
      {"name":"demo.pdf", "data_id":"demo"}
    ],
    "model_version":"pipeline"
  }'

curl -X PUT -T /path/to/demo.pdf 'https://UPLOAD_URL_FROM_MINERU'

curl --location --request GET "https://mineru.net/api/v4/extract-results/batch/$BATCH_ID" \
  --header "Authorization: Bearer $MINERU_API_TOKEN" \
  --header 'Accept: */*'
```
- Useful request options: `is_ocr`, `enable_formula`, `enable_table`, `language`, `page_ranges`, `extra_formats`, `no_cache`, `cache_tolerance`
- Common result fields: `task_id`, `batch_id`, `state`, `err_msg`, `full_zip_url`, `extract_progress`
- Output reference: `https://opendatalab.github.io/MinerU/reference/output_files/`
- Common limits: max `200MB`, max `600` pages, upload URL valid for `24` hours, up to `200` files per batch request, daily priority quota applies.

## Temp and output conventions
- Use `tmp/pdfs/` for intermediate files; delete when done.
- Write final artifacts under `output/pdf/` when working in this repo.
- Keep filenames stable and descriptive.

## Dependencies (install if missing)
Prefer `uv` for dependency management.

Python packages:
```
uv pip install reportlab pdfplumber pypdf requests
```
If `uv` is unavailable:
```
python3 -m pip install reportlab pdfplumber pypdf requests
```
System tools (for rendering):
```
# macOS (Homebrew)
brew install poppler

# Ubuntu/Debian
sudo apt-get install -y poppler-utils
```

If installation isn't possible in this environment, tell the user which dependency is missing and how to install it locally.

## Environment
- In this setup, the shared secret source of truth is `MINERU_API_KEY` in `~/.config/secrets/shared.env`.
- Shell loaders should mirror `MINERU_API_KEY` to `MINERU_API_TOKEN` automatically; if they did not run in the current shell, normalize manually with `export MINERU_API_TOKEN="${MINERU_API_TOKEN:-${MINERU_API_KEY:-}}"`.
- If both env vars are missing, stop and surface that MinerU is unavailable in the current shell instead of silently falling back to stale local notes.
- Prefer reusing shell-managed secret sources such as `shared.env`, `local.env`, or an already-exported session variable over copying a literal token into this skill or any checked-in file.
- Never hardcode MinerU tokens into repo files, checked-in configs, or chat responses.

## Rendering command
```
pdftoppm -png $INPUT_PDF $OUTPUT_PREFIX
```

## Quality expectations
- Maintain polished visual design: consistent typography, spacing, margins, and section hierarchy.
- Avoid rendering issues: clipped text, overlapping elements, broken tables, black squares, or unreadable glyphs.
- Charts, tables, and images must be sharp, aligned, and clearly labeled.
- Use ASCII hyphens only. Avoid U+2011 (non-breaking hyphen) and other Unicode dashes.
- Citations and references must be human-readable; never leave tool tokens or placeholder strings.

## Final checks
- Do not deliver until the latest PNG inspection shows zero visual or formatting defects.
- Confirm headers/footers, page numbering, and section transitions look polished.
- Keep intermediate files organized or remove them after final approval.
