"use strict";

// Exercises onDidParseMarkdown of the generated parser.js in a bare vm context
// — mirroring crossnote's QuickJS sandbox (no window/document/module/require).
// The input HTML mimics what crossnote's `sgi` + `wHs` pipeline emits for a
// fenced block: <pre data-role="codeBlock" data-info="…"><code>ESCAPED</code></pre>.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const parserSource = fs.readFileSync(
  path.resolve(__dirname, "..", "parser.js"),
  "utf8",
);
const parser = vm.runInNewContext(parserSource);

const escapeHtml = (text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const ALGORITHM = String.raw`\begin{algorithm}
\caption{Merge Intervals\\{\small\textit{Semantics: 根据正文重构}}}
\begin{algorithmic}
\INPUT intervals $I$
\STATE sort $I$ by start
\STATE \textcolor{red}{$\mathcal{O}(n \log n)$}
\end{algorithmic}
\end{algorithm}`;

function codeBlock(source, info = "pseudocode", extraAttrs = "") {
  return (
    `<pre data-role="codeBlock" data-info="${escapeHtml(info)}"` +
    `${extraAttrs} class="language-pseudocode"><code>${escapeHtml(source)}</code></pre>`
  );
}

test("prerenders a codeBlock into the same figure markup as the runtime", async () => {
  const html = `<p>before</p>${codeBlock(ALGORITHM, "pseudocode numbered", ' data-source-line="7"')}<p>after</p>`;
  const output = await parser.onDidParseMarkdown(html);

  assert.match(output, /<figure class="crossnote-pseudocode"/);
  assert.match(output, /data-pseudocode-rendered="true"/);
  assert.match(output, /role="figure"/);
  assert.match(output, /aria-labelledby="crossnote-pseudocode-caption-1"/);
  assert.match(output, /id="crossnote-pseudocode-caption-1"/);
  // line numbers via the `numbered` flag in data-info
  assert.match(output, /ps-linenum/);
  // scroll-sync attribute carried over from the <pre>
  assert.match(output, /data-source-line="7"/);
  // manual text colors become spans; math renders through KaTeX
  assert.match(output, /ps-manual-color ps-color-red/);
  assert.match(output, /class="katex"/);
  // no leftover raw block
  assert.doesNotMatch(output, /data-role="codeBlock"/);
  // caption text: pseudocode.js emits `Algorithm 1 ` inside a keyword span
  assert.match(output, />Algorithm 1 <\/span>Merge Intervals/);
});

test("carries custom fence classes and id from the pre to the figure", async () => {
  const html =
    `<pre data-role="codeBlock" data-info="pseudocode" id="algo-1"` +
    ` class="language-pseudocode wide fancy"><code>` +
    escapeHtml(ALGORITHM) +
    `</code></pre>`;
  const output = await parser.onDidParseMarkdown(html);
  assert.match(output, /<figure class="crossnote-pseudocode wide fancy"[^>]*id="algo-1"/);
  assert.doesNotMatch(output, /figure[^>]*language-pseudocode/);
});

test("flag-shaped {...} attrs apply ({numbered})", async () => {
  const html = codeBlock(ALGORITHM, "pseudocode {numbered}");
  const output = await parser.onDidParseMarkdown(html);
  assert.match(output, /ps-linenum/);
});

test("numbers captions sequentially across blocks", async () => {
  const html = codeBlock(ALGORITHM) + codeBlock(ALGORITHM);
  const output = await parser.onDidParseMarkdown(html);
  assert.match(output, />Algorithm 1 <\/span>Merge Intervals/);
  assert.match(output, />Algorithm 2 <\/span>Merge Intervals/);
});

test("leaves non-pseudocode codeBlocks untouched", async () => {
  const html =
    `<pre data-role="codeBlock" data-info="python"><code>print(1)</code></pre>` +
    `<pre data-role="codeBlock" data-info=""><code>x</code></pre>`;
  assert.equal(await parser.onDidParseMarkdown(html), html);
});

test("returns html unchanged when no pseudocode data-info exists", async () => {
  const html = "<p>plain</p>";
  assert.equal(await parser.onDidParseMarkdown(html), html);
});

test("source errors keep the raw block and prepend an error banner", async () => {
  const bad = codeBlock("\\begin{algorithm}\\BOGUS\\end{algorithm}");
  const output = await parser.onDidParseMarkdown(bad);
  assert.match(output, /class="pseudocode-error" role="alert"/);
  assert.match(output, /Pseudocode render error:/);
  // raw <pre> preserved so the client runtime can retry in the preview
  assert.match(output, /data-role="codeBlock"/);
});

test("unsupported text colors surface as render errors", async () => {
  const bad = codeBlock(
    String.raw`\begin{algorithm}
\caption{T}
\begin{algorithmic}
\STATE \textcolor{cyan}{x}
\end{algorithmic}
\end{algorithm}`,
  );
  const output = await parser.onDidParseMarkdown(bad);
  assert.match(output, /Unsupported text color &#39;cyan&#39;/);
});

test("memoized figure re-stamps data-source-line on repeat renders", async () => {
  // The module-level figure cache persists across onDidParseMarkdown calls.
  // A cached figure carries the source line it was rendered with — it must
  // be re-stamped, or scroll-sync lands on a stale line after edits above.
  const first = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM, "pseudocode", ' data-source-line="7"'),
  );
  const second = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM, "pseudocode", ' data-source-line="42"'),
  );
  assert.match(second, /data-source-line="42"/);
  assert.doesNotMatch(second, /data-source-line="7"/);
  // Identical markup modulo the re-stamped attribute.
  assert.equal(
    second.replace('data-source-line="42"', 'data-source-line="7"'),
    first,
  );
});

test("figure cache keys include the pre's id and custom classes", async () => {
  // Same source + info + captionIndex but different {.cls #id} attrs must
  // not share a cache entry — the attrs are baked into the figure markup.
  const withId = await parser.onDidParseMarkdown(
    `<pre data-role="codeBlock" data-info="pseudocode" id="algo-x"` +
      ` class="language-pseudocode wide"><code>${escapeHtml(ALGORITHM)}</code></pre>`,
  );
  assert.match(withId, /id="algo-x"/);
  assert.match(withId, /class="crossnote-pseudocode wide"/);

  const plain = await parser.onDidParseMarkdown(codeBlock(ALGORITHM));
  assert.doesNotMatch(plain, /algo-x|wide/);
});

test("literal sentinel digits in inputs bypass the re-stamp cache", async () => {
  // Cached figures render with a sentinel caption index and get "7777778"
  // re-stamped to the real number on a hit. When those digits appear in the
  // source or attrs themselves, the stamp would rewrite content too — dirty
  // inputs must skip the cache and render the real index directly.
  const dirty = String.raw`\begin{algorithm}
\caption{Case 7777778\\{\small\textit{Semantics: 根据正文重构}}}
\begin{algorithmic}
\STATE $x \gets x$
\end{algorithmic}
\end{algorithm}`;

  const first = await parser.onDidParseMarkdown(
    codeBlock(dirty, "pseudocode", ' id="note-7777778"'),
  );
  assert.match(first, />Algorithm 1 <\/span>Case 7777778/);
  assert.match(first, /id="note-7777778"/);

  // Same block under a later caption: only the number moves — content and id
  // digits stay literal (a sentinel cache hit would turn them into "2").
  const second = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM) + codeBlock(dirty, "pseudocode", ' id="note-7777778"'),
  );
  assert.match(second, />Algorithm 1 <\/span>Merge Intervals/);
  assert.match(second, />Algorithm 2 <\/span>Case 7777778/);
  assert.match(second, /id="note-7777778"/);
});

test("sentinel digits in data-info and custom classes also bypass the cache", async () => {
  // The dirty guard covers every attr that lands in the figure markup, not
  // just source/id — a title or fence class carrying the digits must not be
  // rewritten by a later cache-hit stamp. (title= replaces the "Algorithm"
  // label, so the caption keyword becomes the title text.)
  const output = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM) +
      codeBlock(ALGORITHM, "pseudocode title=C7777778x") +
      `<pre data-role="codeBlock" data-info="pseudocode"` +
      ` class="language-pseudocode w7777778"><code>` +
      escapeHtml(ALGORITHM) +
      `</code></pre>`,
  );
  assert.match(output, />Algorithm 1 <\/span>Merge Intervals/);
  // real index 2 stamped; the title digits stay literal — a dirty cache hit
  // would have stamped "7777778" inside the title/class into the number.
  assert.match(output, />C7777778x 2 <\/span>Merge Intervals/);
  assert.match(output, />Algorithm 3 <\/span>Merge Intervals/);
  assert.match(output, /crossnote-pseudocode w7777778/);
  assert.doesNotMatch(output, /7777779/);
});

test("multi-\\caption blocks consume real numbers — no sentinel leak", async () => {
  // The vendored renderer bumps its caption counter once per \caption but
  // only the last caption renders — a 2-\caption block displays "Algorithm 2"
  // and consumes 2 numbers. The sentinel stamp covers exactly one number, so
  // these blocks must render the real index directly (sentinel+1 would leak
  // as "Algorithm 7777779").
  const two = String.raw`\begin{algorithm}
\caption{First\\{\small\textit{Semantics: 根据正文重构}}}
\caption{Second}
\begin{algorithmic}
\STATE $x \gets x$
\end{algorithmic}
\end{algorithm}`;
  const output = await parser.onDidParseMarkdown(
    codeBlock(two) + codeBlock(ALGORITHM),
  );
  assert.match(output, /data-caption-index="1" data-caption-count="2"/);
  assert.match(output, />Algorithm 2 <\/span>Second/);
  // the block after a 2-\caption figure continues at 3, not 2
  assert.match(output, />Algorithm 3 <\/span>Merge Intervals/);
  assert.doesNotMatch(output, /777777\d/);
});

test("cache key strips data-source-line embedded in data-info", async () => {
  // MPE emits the volatile line inside data-info on some paths — it must be
  // stripped from the key or every line edit would invalidate the cache.
  const line7 = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM, "pseudocode {data-source-line=7}"),
  );
  const line42 = await parser.onDidParseMarkdown(
    codeBlock(ALGORITHM, "pseudocode {data-source-line=42}"),
  );
  // Cache hit: identical figure markup, and the info-embedded line is not a
  // render option so nothing else differs either.
  assert.equal(line42, line7);
});

test("figure cache stays correct past the 512-entry bound", async () => {
  // Eviction is LRU by count AND bytes — render past the count cap and
  // confirm entries still stamp correctly (no sentinel leak, right numbers).
  const total = 516;
  let html = "";
  for (let i = 0; i < total; i += 1) {
    html += codeBlock(
      ALGORITHM.replace("Merge Intervals", "Algo " + i).replace(
        "$\\mathcal{O}(n \\log n)$",
        "$x_{" + i + "}$",
      ),
    );
  }
  const output = await parser.onDidParseMarkdown(html);
  assert.doesNotMatch(output, /777777\d/);
  assert.match(output, />Algorithm 1 <\/span>Algo 0/);
  assert.match(output, new RegExp(">Algorithm " + total + " </span>Algo " + (total - 1)));
});

test("a % line comment hides \\textcolor and \\caption from preprocessing", async () => {
  // TeX comments run to end of line — a commented-out \textcolor or \caption
  // must not trip the color gate or consume a caption number.
  const commented = String.raw`\begin{algorithm}
\caption{Real\\{\small\textit{Semantics: 根据正文重构}}}
% \caption{CommentedOut}
\begin{algorithmic}
\STATE keep % \textcolor{cyan}{commented}
\end{algorithmic}
\end{algorithm}`;
  const output = await parser.onDidParseMarkdown(
    codeBlock(commented) + codeBlock(ALGORITHM),
  );
  assert.doesNotMatch(output, /pseudocode-error/);
  // % \caption did not consume a number — the next block is 2, not 3
  assert.match(output, />Algorithm 1 <\/span>Real/);
  assert.match(output, />Algorithm 2 <\/span>Merge Intervals/);
});

test("a % inside a \\textcolor body gets a targeted error, not a parse fail", async () => {
  const bad = String.raw`\begin{algorithm}
\caption{T}
\begin{algorithmic}
\STATE \textcolor{red}{a % b}
\end{algorithmic}
\end{algorithm}`;
  const output = await parser.onDidParseMarkdown(codeBlock(bad));
  assert.match(output, /pseudocode-error/);
  assert.match(output, /% comment/);
});

test("a <pre> without a <code> child still renders via the tag-slice fallback", async () => {
  const html =
    `<pre data-role="codeBlock" data-info="pseudocode" ` +
    `class="language-pseudocode">${escapeHtml(ALGORITHM)}</pre>`;
  const output = await parser.onDidParseMarkdown(html);
  assert.match(output, /<figure class="crossnote-pseudocode"/);
  assert.match(output, />Algorithm 1 <\/span>Merge Intervals/);
});

test("pseudocode-* info strings are not our fence — block untouched", async () => {
  const html =
    `<pre data-role="codeBlock" data-info="pseudocode-extra" ` +
    `class="language-pseudocode-extra"><code>x</code></pre>`;
  assert.equal(await parser.onDidParseMarkdown(html), html);
});

test("&-entities in data-info and id are decoded on the render path", async () => {
  const html =
    `<pre data-role="codeBlock" data-info="pseudocode title=Foo&amp;Bar"` +
    ` id="a&amp;b" class="language-pseudocode"><code>` +
    escapeHtml(ALGORITHM) +
    `</code></pre>`;
  const output = await parser.onDidParseMarkdown(html);
  assert.match(output, /<figure class="crossnote-pseudocode"/);
  // attrs decoded then re-escaped into markup
  assert.match(output, /id="a(&amp;|&)b"/);
  assert.match(output, /Foo(&amp;|&) *Bar|Foo(&amp;|&)Bar/);
});

test("PRE_ID requires a real id attribute — data-id/x-id are not stolen", async () => {
  const onlyDataId =
    `<pre data-role="codeBlock" data-info="pseudocode" data-id="stolen"` +
    ` class="language-pseudocode"><code>${escapeHtml(ALGORITHM)}</code></pre>`;
  const out1 = await parser.onDidParseMarkdown(onlyDataId);
  assert.doesNotMatch(out1, /id="stolen"/);

  const both =
    `<pre data-role="codeBlock" data-info="pseudocode" data-id="decoy"` +
    ` id="real-1" class="language-pseudocode"><code>${escapeHtml(ALGORITHM)}</code></pre>`;
  const out2 = await parser.onDidParseMarkdown(both);
  assert.match(out2, /id="real-1"/);
  assert.doesNotMatch(out2, /id="decoy"/);
});
