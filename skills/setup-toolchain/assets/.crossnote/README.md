# .crossnote — Markdown Preview Enhanced workspace config

Renders ` ```pseudocode ` fenced blocks (LaTeX `algorithm`/`algorithmic` syntax) in preview **and** exports, via [pseudocode.js](vendor/README.md).

## How it works

- `parser.js` runs inside crossnote's QuickJS WASM sandbox — a single expression, no `require`/`fs`/`window`. Its `onWillParseMarkdown` injects `@import "/.crossnote/theme-toggle.js"` into **every** note (preview chrome) plus `@import "/.crossnote/pseudocode-runtime.js"` only into notes containing a pseudocode fence; its `onDidParseMarkdown` **prerenders** each `<pre data-role="codeBlock" data-info="pseudocode…">` into the final `<figure>` markup, so HTML export and print/PDF get rendered algorithms too.
- `pseudocode-runtime.js` is the client-side fallback (MutationObserver + lazy vendor loading) for the rare case the sandbox hook fails. Its DOM-free core is marked `BEGIN/END PURE CORE` — that slice is shared with the parser and with `scripts/check-pseudocode.cjs`.
- `theme-toggle.js` is the floating appearance picker (bottom-right): opens an 8-slot popup menu — 跟随系统 / 跟随编辑器 / 暖纸 / 羊皮纸 / 雪白 / 暖黑 / One Dark / 纯黑，each shown as a two-tone {paper, ink} swatch — writes `body[data-xnote-theme]`, persists in the webview's localStorage (new preview pane = fresh origin = back to `system`; legacy `light`/`dark` values map to `paper`/`dark`). `style.less` resolves the attribute to palettes. Exported HTML gets a dead `/.crossnote/` script path (no button); `@media print` hides it in PDF.
- `vendor/` pins `katex-0.16.47` (must match MPE's bundled build, **not** upstream — v0.18 renamed CSS classes) and `pseudocode-2.4.1`.
- `style.less` is the preview theme (midvok) plus the pseudocode styles —it ships to exports via crossnote's `globalCss`. Colors follow the texlate slot model (pdfTheme.ts `paletteChromeVars`, ADR-0020): each slot is a {bg, fg} pair and every surface/text/border var is derived by `#paper-slot-light()` / `#paper-slot-dark()` via `color-mix` at fixed ratios, so chrome can never mismatch the paper. `:root` carries `paper` (暖纸) as the default; `body[data-xnote-theme="sepia"|"snow"|"dark"|"onedark"|"black"]` picks a named slot; `editor` delegates to MPE's `.markdown-preview.editor-dark`/`.editor-light` tags (→ 暖黑 / paper); absent/`system` follows `prefers-color-scheme` directly → 暖黑 on a dark OS (no MPE tag needed — exported HTML follows the reader's OS too) — all inside `@media screen` (keep `markdown-preview-enhanced.previewColorScheme` at `systemColorScheme` so OS flips still push a refresh that re-tags the `editor-*` classes) while print/export stays on `:root` paper. Callout text lightness is tunable per scheme via `--callout-text-shift` (0 on dark slots). Also on board: Obsidian-style `> [!type]` callouts + admonitions on one slot-palette pipeline, footnote styling (muted block, 30% separator, `:target` backref highlight), front-matter typography classes (`readable`/`wide`/`fullwidth`/`justify`/`lh15`/`lh17`/`lh2`/`bold`, plus `invertimg` to flip black-background diagrams back to light on dark slots), Zotero-style `brightness(0.85)` dimming of images/SVGs on dark slots (the lightbox restores originals), and finer print page-break granularity (`li`/`tr` row-level avoids + repeated `thead` + orphans/widows instead of pushing whole lists/tables over). `~/.local/state/crossnote/style.less` — the MPE global layer — is a symlink to this file, so workspaces without a `.crossnote/` farm still get the theme (the global parser.js stays the default stub: no script injection there).
- `head.html` may only contain link/style/meta — `<script>` is stripped by crossnote ≥0.9.31.
- `config.js` only reaches keys the extension does NOT register as VS Code settings (katexConfig/mathjaxConfig/mermaidConfig). Editor-registered keys belong in `.vscode/settings.json` (gitignored, machine-local).

## Build

`parser.js`'s GENERATED section embeds the vendored builds + the PURE CORE slice. After touching `vendor/*` or that slice:

```sh
node .crossnote/scripts/build-parser.cjs        # regenerate
node .crossnote/scripts/build-parser.cjs --check  # freshness check (pre-commit)
```

## Lint & test

```sh
# 经目录软链共享：脚本永远 lint "cwd 所在仓"，不是脚本所在目录
node .crossnote/scripts/check-pseudocode.cjs          # sweep tracked .md in the cwd repo
node .crossnote/scripts/check-pseudocode.cjs --staged # staged .md of that repo (pre-commit)
node --test .crossnote/tests/*.test.cjs               # full suite
```

Fence info options: `numbered` / `linenum`, `noend`, `scopelines`,
`title=前缀`, `indent=1.5em` (em only), `linepunc=.`, `commentdelim=▷`. See the `伪代码` section of the vault's [AGENTS.md](../AGENTS.md#伪代码) (maintained in the obsidian vault) for the writing conventions.
