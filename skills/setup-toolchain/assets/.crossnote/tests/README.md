# Pseudocode runtime tests

Run the regression suite from the vault root:

```sh
node --test .crossnote/tests/*.test.cjs
```

Browser-level tests (`pseudocode-runtime.test.cjs`) use an installed `playwright` package when available, falling back to the locally installed Google Chrome when the Playwright-managed Chromium build is missing.

Pure-Node tests (`parser.test.cjs`, `parser-prerender.test.cjs`, `pseudocode-options.test.cjs`, `pseudocode-source.test.cjs`, `check-pseudocode.test.cjs`, `parser-build.test.cjs`, `vendor-integrity.test.cjs`) need no browser.
`parser-prerender.test.cjs` evaluates the generated `parser.js` in a bare `vm` context — mirroring crossnote's QuickJS sandbox — and feeds synthetic `<pre data-role="codeBlock">` HTML through `onDidParseMarkdown`. `pseudocode-source.test.cjs` runs the same check as `.crossnote/scripts/check-pseudocode.cjs`, which is also wired into the git pre-commit hook for staged `.md` files. `vendor-integrity.test.cjs` verifies the SHA-256 checksums documented in `vendor/README.md`.

## Generated parser.js

`parser.js` embeds the vendored KaTeX + pseudocode.js builds and the PURE CORE slice of `pseudocode-runtime.js` between its `GENERATED` markers —crossnote's sandbox has no `require`/`fs`, so the code must be inlined.
After changing `vendor/*` or the marked slice, regenerate with:

```sh
node .crossnote/scripts/build-parser.cjs
```

`parser-build.test.cjs` (and the pre-commit hook) run the same command with `--check` and fail when the generated section is stale.

`parser-quickjs.test.cjs` is optional: it evaluates `parser.js` inside a real QuickJS WASM runtime — the engine crossnote sandboxes hooks in — and skips unless `quickjs-emscripten` is resolvable (`npm install --no-save quickjs-emscripten`).

`bench-profile.cjs` is not a test — it profiles the hooks: per-render timings through the real QuickJS string-marshal boundary (and a `vm` baseline), cold-vs-memoized pseudocode prerender, eval/init cost, and end-to-end `parseMD` via the `crossnote` package when resolvable. Run `node tests/bench-profile.cjs`; deps come from `--deps=<dir>`/`$BENCH_DEPS` (needs `quickjs-emscripten-core`, `@jitl/quickjs-singlefile-cjs-release-sync`; optional `markdown-it`, `crossnote`), corpus via `--corpus=a.md,b.md`, plus `--repeat=N`, `--no-e2e`, `--json`.
