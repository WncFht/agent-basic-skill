"use strict";

// High-fidelity sandbox test: evaluates the generated parser.js inside a real
// QuickJS WASM runtime — the same engine crossnote uses — with the same
// mechanics (single-expression eval, 5s interrupt deadline, 64MB limit,
// string marshal in/out of the hooks).
//
// Optional: skipped unless `quickjs-emscripten` is resolvable. To enable:
//   npm install --no-save quickjs-emscripten   (from the vault root)

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

let getQuickJS = null;
try {
  ({ getQuickJS } = require("quickjs-emscripten"));
} catch {
  /* module not installed — the test below skips */
}
if (!getQuickJS) {
  process.emitWarning(
    "quickjs-emscripten not resolvable; skipping QuickJS sandbox parity test",
  );
}

const parserSource = fs.readFileSync(
  path.resolve(__dirname, "..", "parser.js"),
  "utf8",
);
// crossnote wraps the file as a single expression before eval.
const wrapped = "(" + parserSource.trim().replace(/[;,]+$/, "") + ")";

const escapeHtml = (text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const ALGORITHM = String.raw`\begin{algorithm}
\caption{Merge Intervals}
\begin{algorithmic}
\STATE sort $I$
\STATE \textcolor{red}{$\mathcal{O}(n)$}
\end{algorithmic}
\end{algorithm}`;

test(
  "parser.js evaluates and prerenders inside real QuickJS",
  { skip: !getQuickJS },
  async () => {
    const QuickJS = await getQuickJS();
    const ctx = QuickJS.newContext();
    const deadline = Date.now() + 5000;
    ctx.runtime.setInterruptHandler(() => Date.now() > deadline);
    ctx.runtime.setMemoryLimit(64 * 1024 * 1024);

    const evalResult = ctx.evalCode(wrapped);
    assert.ok(!evalResult.error, "parser.js must eval as one expression");
    ctx.setProp(ctx.global, "__hooks", evalResult.value);
    evalResult.value.dispose();

    const callHook = (name, input) => {
      const code =
        `__hooks[${JSON.stringify(name)}](${JSON.stringify(input)})` +
        `.then(v => { globalThis.__out = String(v); })` +
        `.catch(e => { globalThis.__out = "__ERR__" + (e && e.message || e); })`;
      const r = ctx.evalCode(code);
      assert.ok(!r.error, "hook call threw synchronously");
      r.value.dispose();
      ctx.runtime.executePendingJobs();
      const out = ctx.getProp(ctx.global, "__out");
      const value = ctx.dump(out);
      if (out && out.dispose) out.dispose();
      const clear = ctx.evalCode("globalThis.__out = undefined");
      if (clear.value) clear.value.dispose();
      if (clear.error) clear.error.dispose();
      assert.ok(
        typeof value === "string" && !value.startsWith("__ERR__"),
        `hook returned error: ${String(value).slice(0, 200)}`,
      );
      return value;
    };

    const html =
      `<pre data-role="codeBlock" data-info="pseudocode numbered"` +
      ` data-source-line="3" class="language-pseudocode"><code>` +
      escapeHtml(ALGORITHM) +
      `</code></pre>`;
    const output = callHook("onDidParseMarkdown", html);
    assert.match(output, /class="crossnote-pseudocode"/);
    assert.match(output, /class="katex"/);
    assert.match(output, /ps-color-red/);
    assert.match(output, /ps-linenum/);
    assert.match(output, /data-source-line="3"/);
    ctx.dispose();
  },
);
