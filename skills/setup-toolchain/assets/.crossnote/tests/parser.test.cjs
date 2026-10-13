"use strict";

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

const PSEUDOCODE = "```pseudocode\n\\begin{algorithm}\n\\begin{algorithmic}\n\\STATE x\n\\end{algorithmic}\n\\end{algorithm}\n```\n";

test("injects theme toggle into every note, runtime only with a fence", async () => {
  const output = await parser.onWillParseMarkdown("# Note\n" + PSEUDOCODE);
  assert.match(output, /<!-- crossnote-theme-toggle -->/);
  assert.match(output, /@import "\/.crossnote\/theme-toggle\.js";/);
  assert.match(output, /<!-- crossnote-pseudocode-runtime -->/);
  assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
  assert.doesNotMatch(output, /vendor\/katex|vendor\/pseudocode/);
});

test("notes without a pseudocode fence get only the theme toggle", async () => {
  for (const markdown of [
    "# Note\nplain text\n",
    "```js\nconsole.log(1)\n```\n",
    "```pseudocode-extra\nnot ours\n```\n",
    "A mention of ```pseudocode inside an inline span\n",
  ]) {
    const output = await parser.onWillParseMarkdown(markdown);
    assert.match(output, /@import "\/.crossnote\/theme-toggle\.js";/);
    assert.doesNotMatch(output, /pseudocode-runtime/);
  }
});

test("recognizes tilde, 4+-backtick, and indented fences", async () => {
  for (const fence of [
    "~~~pseudocode\nx\n~~~\n",
    "````pseudocode\nx\n````\n",
    "   ```pseudocode\nx\n   ```\n",
    "```pseudocode numbered title=Foo\nx\n```\n",
    "> quote\n> ```pseudocode\n> x\n> ```\n", // blockquote-nested renders too
  ]) {
    const output = await parser.onWillParseMarkdown("# N\n" + fence);
    assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
  }
});

test("recognizes list-nested, ::: colon, and mixed-container fences", async () => {
  for (const fence of [
    "- item\n  ```pseudocode\n  x\n  ```\n",
    "1. item\n   ```pseudocode\n   x\n   ```\n",
    "- ```pseudocode\n  x\n  ```\n", // fence opens on the marker line itself
    ":::pseudocode\nx\n:::\n",
    "> - ```pseudocode\n  > x\n  > ```\n",
  ]) {
    const output = await parser.onWillParseMarkdown("# N\n" + fence);
    assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
  }
});

test("lang gate is case-insensitive and accepts {-attached options", async () => {
  for (const fence of [
    "```Pseudocode\nx\n```\n",
    "```PSEUDOCODE\nx\n```\n",
    "```pseudocode{numbered}\nx\n```\n",
    "~~~Pseudocode\nx\n~~~\n",
  ]) {
    const output = await parser.onWillParseMarkdown("# N\n" + fence);
    assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
  }
});

test("a tab-indented 'fence' is indented code — no injection", async () => {
  // CommonMark: a leading tab already reaches column 4, so the line is an
  // indented code block, not a fence. check-pseudocode scans the same way.
  const output = await parser.onWillParseMarkdown(
    "# N\n\t```pseudocode\n\tx\n\t```\n",
  );
  assert.doesNotMatch(output, /pseudocode-runtime/);
});

test("appends the imports at end of document, front matter untouched", async () => {
  // Imports land at EOF (not after FM): lines added at the top would inflate
  // data-source-line for everything below and break preview scroll-sync.
  const markdown = "---\ntitle: Test\n---\n# Note\n" + PSEUDOCODE;
  const output = await parser.onWillParseMarkdown(markdown);
  assert.match(output, /^---\ntitle: Test\n---\n# Note\n/);
  assert.match(
    output,
    /\n\n<!-- crossnote-theme-toggle -->\n@import "\/.crossnote\/theme-toggle\.js";\n<!-- crossnote-pseudocode-runtime -->\n@import "\/.crossnote\/pseudocode-runtime\.js";\n$/,
  );
});

test("treats ---\\n--- as empty front matter, like crossnote", async () => {
  // cdt detects FM via startsWith("---") + indexOf("\n---"), so a bare
  // "---\n---" pair is consumed as (empty) FM. The FM block stays untouched
  // at the top; the imports append after the body.
  const markdown = "---\n---\n# Note\n\n---\n\n" + PSEUDOCODE;
  const output = await parser.onWillParseMarkdown(markdown);
  assert.match(output, /^---\n---\n# Note\n\n---\n\n/);
  assert.match(
    output,
    /@import "\/.crossnote\/pseudocode-runtime\.js";\n$/,
  );
});

test("appends imports at end of document when there is no front matter", async () => {
  for (const markdown of [
    "# Note\n" + PSEUDOCODE,
    "---\nunclosed: yes\n# Note\n" + PSEUDOCODE, // unclosed: no \n--- line
    "﻿---\nx: 1\n---\n" + PSEUDOCODE, // BOM defeats startsWith — same as crossnote
  ]) {
    const output = await parser.onWillParseMarkdown(markdown);
    assert.ok(
      output.endsWith('@import "/.crossnote/pseudocode-runtime.js";\n'),
    );
    assert.ok(output.indexOf("<!-- crossnote-theme-toggle -->") > 0);
  }
});

test("falls back to post-front-matter injection inside an unclosed fence", async () => {
  // A doc ending inside an open fence would swallow an EOF import into the
  // code block — the import must go after the front matter instead.
  const markdown = "---\nt: 1\n---\n# Note\n```pseudocode\nx\n";
  const output = await parser.onWillParseMarkdown(markdown);
  assert.match(
    output,
    /^---\nt: 1\n---\n<!-- crossnote-theme-toggle -->\n@import "\/.crossnote\/theme-toggle\.js";\n<!-- crossnote-pseudocode-runtime -->\n@import "\/.crossnote\/pseudocode-runtime\.js";\n\n# Note\n```pseudocode\nx\n$/,
  );
});

test("an outer 4+-backtick fence swallows an inner pseudocode fence", async () => {
  // ````markdown examples documenting a ```pseudocode fence render it as
  // literal body text — injecting the runtime there is wasted fetch+eval.
  const markdown =
    "# N\n````markdown\n```pseudocode\nx\n```\n````\nplain\n";
  const output = await parser.onWillParseMarkdown(markdown);
  assert.doesNotMatch(output, /pseudocode-runtime/);
  assert.match(output, /@import "\/.crossnote\/theme-toggle\.js";/);
});

test("a tilde fence swallows backtick fences inside it", async () => {
  const markdown = "# N\n~~~text\n```pseudocode\nx\n```\n~~~\n";
  const output = await parser.onWillParseMarkdown(markdown);
  assert.doesNotMatch(output, /pseudocode-runtime/);
});

test("an unclosed pseudocode fence still injects (mid-typing)", async () => {
  // CommonMark renders an unclosed fence to end of document — the runtime
  // must be present for the in-progress render.
  const output = await parser.onWillParseMarkdown("# N\n```pseudocode\nx\n");
  assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
});

test("a pseudocode fence after an earlier fence still injects", async () => {
  const markdown = "```js\nconsole.log(1)\n```\n" + PSEUDOCODE;
  const output = await parser.onWillParseMarkdown(markdown);
  assert.match(output, /@import "\/.crossnote\/pseudocode-runtime\.js";/);
});

test("does not inject the imports twice", async () => {
  const once = await parser.onWillParseMarkdown("# Note\n" + PSEUDOCODE);
  const twice = await parser.onWillParseMarkdown(once);
  assert.equal(twice, once);
  assert.equal((twice.match(/crossnote-pseudocode-runtime/g) || []).length, 1);
  assert.equal((twice.match(/crossnote-theme-toggle/g) || []).length, 1);
});

test("vendored KaTeX/pseudocode eval lazily — only on first real render", async () => {
  // The ~640KB vendored sources are spliced in as strings and eval'd by
  // ensureVendoredGlobals on the first prerendered block. In a vm sandbox the
  // UMD globals land on the context object, so laziness is observable.
  const sandbox = {};
  const lazy = vm.runInNewContext(parserSource, sandbox);
  await lazy.onWillParseMarkdown("# Note\n```js\nx\n```\n");
  await lazy.onDidParseMarkdown("<p>plain</p><pre><code>x</code></pre>");
  assert.equal(sandbox.katex, undefined);
  assert.equal(sandbox.pseudocode, undefined);

  const algo = String.raw`\begin{algorithm}
\caption{T}
\begin{algorithmic}
\STATE x
\end{algorithmic}
\end{algorithm}`;
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const html =
    `<pre data-role="codeBlock" data-info="pseudocode" ` +
    `class="language-pseudocode"><code>${esc(algo)}</code></pre>`;
  const output = await lazy.onDidParseMarkdown(html);
  assert.match(output, /crossnote-pseudocode/);
  assert.ok(sandbox.katex);
  assert.ok(sandbox.pseudocode);
});
