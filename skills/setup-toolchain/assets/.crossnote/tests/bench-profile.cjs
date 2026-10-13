"use strict";

// bench-profile.cjs — reproducible perf profile of the .crossnote parser hooks.
//
// Measures parser.js the way crossnote 0.9.30+ actually runs it: the file is
// eval'd as ONE expression inside a QuickJS WASM sandbox, and every hook call
// marshals the whole markdown/HTML string in and out of the sandbox. We drive
// the same mechanics from Node (quickjs-emscripten-core + the same
// singlefile-cjs-release-sync variant crossnote requires), alongside a plain
// `vm` baseline that shows what the same code costs under a JIT.
//
// onDidParseMarkdown is fed REAL crossnote HTML: a throwaway notebook whose
// generated default parser.js is the identity hook produces exactly the
// <pre data-role="codeBlock"> markup the prerender pass scans for (and a
// full-pipeline baseline without our hook logic).
//
// Usage:
//   node tests/bench-profile.cjs [--deps=DIR[:DIR...]] [--corpus=a.md,b.md]
//     [--repeat=N] [--deadline=MS] [--synthetic-lines=N] [--no-e2e] [--json]
//
// Deps resolution (first hit wins): --deps dirs, $BENCH_DEPS, then the
// well-known crossnote-bench node_modules. Needed: quickjs-emscripten-core,
// @jitl/quickjs-singlefile-cjs-release-sync; optional: markdown-it (fallback
// HTML when crossnote is absent), crossnote (real HTML + end-to-end parseMD).

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { performance } = require("node:perf_hooks");
const { createRequire } = require("node:module");

const CROSSNOTE_DIR = path.resolve(__dirname, "..");
const PARSER_PATH = path.join(CROSSNOTE_DIR, "parser.js");
// Production hook deadline in crossnote's tL (J4) — calls slower than this are
// killed mid-preview. We measure with a generous deadline but flag overruns.
const PROD_HOOK_DEADLINE_MS = 5000;

const now = () => performance.now();
const fmt = (ms) => (ms >= 100 ? ms.toFixed(0) : ms.toFixed(1));
const kb = (n) => (n / 1024).toFixed(1) + "KB";

// ---------------------------------------------------------------- args ----
const argv = process.argv.slice(2);
const opt = {
  repeat: 3,
  deadline: 60000,
  syntheticLines: 3000,
  e2e: true,
  json: false,
};
const depsDirs = [];
let corpusOverride = null;
for (const a of argv) {
  if (a.startsWith("--deps=")) depsDirs.push(...a.slice(7).split(":"));
  else if (a.startsWith("--corpus=")) corpusOverride = a.slice(9).split(",");
  else if (a.startsWith("--repeat=")) opt.repeat = +a.slice(9);
  else if (a.startsWith("--deadline=")) opt.deadline = +a.slice(11);
  else if (a.startsWith("--synthetic-lines=")) opt.syntheticLines = +a.slice(18);
  else if (a === "--no-e2e") opt.e2e = false;
  else if (a === "--json") opt.json = true;
}
if (process.env.BENCH_DEPS) depsDirs.push(...process.env.BENCH_DEPS.split(":"));
// Last-resort default: a local scratch dir holding the bench node_modules.
// Machine-specific, so override via BENCH_DEPS (and skip when absent) rather
// than letting a stale path sit in the resolution chain forever.
const benchDepsDefault =
  process.env.CROSSNOTE_BENCH_DIR ||
  "/home/fanghaotian/tmp-quarantine-20260922/crossnote-bench";
if (fs.existsSync(benchDepsDefault)) depsDirs.push(benchDepsDefault);

function resolveDep(name) {
  for (const dir of depsDirs) {
    try {
      return createRequire(path.join(dir, "package.json"))(name);
    } catch {
      /* try next dir */
    }
  }
  return null;
}

// --------------------------------------------------------------- corpus ----
// Default corpus samples one vault for realistic notes — override with
// BENCH_VAULT (whole set) or --corpus (explicit files) on other machines.
const VAULT = process.env.BENCH_VAULT || "/home/fanghaotian/src/obsidian";
const DEFAULT_CORPUS = [
  ["kitchen-sink", path.join(CROSSNOTE_DIR, "tests/fixtures/kitchen-sink.md")],
  [
    "typical-note",
    path.join(VAULT, "科研/papers/original/2026-07-07--paper--2607.05804--turnopd.md"),
  ],
  ["toc-written", path.join(VAULT, "科研/paper ToC - written.md")],
  [
    "csapp-blog",
    path.join(
      VAULT,
      "计算机/公开课/CSAPP/深入理解计算机系统（CSAPP）含 lab 详解 完结 - CSDN 博客.md",
    ),
  ],
  ["rl-textbook", path.join(VAULT, "pdf/RL Introduction/强化学习-第2版.md")],
];

function genSynthetic(totalLines, pseudoCount) {
  const PSEUDO = String.raw`\begin{algorithm}
\caption{SyntheticAlgo\\{\small\textit{Semantics: 根据正文重构}}}
\begin{algorithmic}
\INPUT batch $B$; steps $T$
\OUTPUT $\theta$
\FOR{$t = 1$ \TO $T$}
    \STATE $g_t \gets \nabla_\theta \mathcal{L}(x_t; \theta)$
    \STATE $\theta \gets \theta - \eta\, \textcolor{red}{g_t}$
\ENDFOR
\RETURN $\theta$
\end{algorithmic}
\end{algorithm}`;
  const out = ["---", 'class: "serif"', "---", "", "# Synthetic stress doc", ""];
  let emitted = 0;
  let nextPseudoAt = Math.floor(totalLines / pseudoCount);
  while (out.length < totalLines) {
    if (emitted < pseudoCount && out.length >= nextPseudoAt) {
      out.push("```pseudocode", PSEUDO, "```", "");
      emitted++;
      nextPseudoAt += Math.floor(totalLines / pseudoCount);
      continue;
    }
    switch (out.length % 5) {
      case 0:
        out.push(
          "## Section " + out.length,
          "",
          "Paragraph with _inline math_ $e^{i\\pi} + 1 = 0$ and `code` and **bold**.",
          "",
        );
        break;
      case 1:
        out.push(
          "$$",
          "\\mathcal{L} = \\sum_{i=1}^{N} \\lVert f_\\theta(x_i) - y_i \\rVert^2 + \\lambda \\lVert \\theta \\rVert_2^2",
          "$$",
          "",
        );
        break;
      case 2:
        out.push("```python", "def f(x):", "    return x * " + out.length, "```", "");
        break;
      case 3:
        out.push(
          "| col A | col B |",
          "| ----- | ----- |",
          "| a" + out.length + " | b |",
          "| c | d |",
          "",
        );
        break;
      default:
        out.push(
          "> [!note] Callout " + out.length,
          "> Body text with a [link](https://example.com) and ==mark==.",
          "",
        );
    }
  }
  return out.join("\n");
}

// ------------------------------------------------------------- html gen ----
// Fallback when crossnote is unavailable: markdown-it with a fence override
// that reproduces crossnote's exact codeBlock shape —
//   <pre data-role="codeBlock" data-info="<info>" data-source-line="N"
//        class="language-x"><code>ESCAPED</code></pre>
function makeHtmlRenderer(markdownIt) {
  if (!markdownIt) {
    return (md) => {
      const esc = (s) =>
        s
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      const blocks = [];
      const re = /^[ \t]{0,3}(`{3,}|~{3,})([^\n]*)\n([\s\S]*?)^[ \t]{0,3}\1[ \t]*$/gm;
      let m;
      while ((m = re.exec(md))) {
        blocks.push(
          `<pre data-role="codeBlock" data-info="${esc(m[2].trim())}" ` +
            `data-source-line="1" class="language-${esc(m[2].trim().split(/\s+/)[0] || "")}">` +
            `<code>${esc(m[3])}</code></pre>`,
        );
      }
      return blocks.join("\n");
    };
  }
  const md = new markdownIt({ html: true, linkify: false, highlight: null });
  const esc = md.utils.escapeHtml;
  md.renderer.rules.fence = (tokens, idx) => {
    const t = tokens[idx];
    const info = t.info ? esc(t.info.trim()) : "";
    const lang = info.split(/\s+/)[0] || "";
    const line = t.map && t.map[0] != null ? String(t.map[0] + 1) : "";
    return (
      `<pre data-role="codeBlock" data-info="${info}" data-source-line="${line}" ` +
      `class="language-${lang}"><code>${esc(t.content)}</code></pre>\n`
    );
  };
  return (source) => md.render(source);
}

// ------------------------------------------------------- node eval path ----
function loadParserNode(source) {
  const t0 = now();
  const parser = vm.runInNewContext(source);
  return { parser, initMs: now() - t0 };
}

// ------------------------------------------------------- quickjs path ------
// Mirrors crossnote's tL(): the WASM module is loaded once and cached (Z2/VA),
// each parser load gets a fresh runtime+context (64MB limit, interrupt
// deadline), the source is eval'd as ONE expression via a trampoline exposing
// __crossnoteCallHook, and every call marshals input via newString and the
// result back via dump.
async function loadParserQuickJS(mod, parserSource, deadlineMs) {
  const timings = {};
  let t = now();
  const rt = mod.newRuntime();
  rt.setMemoryLimit(64 * 1024 * 1024);
  let deadline = 0;
  rt.setInterruptHandler(() => Date.now() > deadline);
  const ctx = rt.newContext();
  timings.contextMs = now() - t;

  const wrap = (s) => `(${s.trim().replace(/[;,]+$/, "")})`;
  const trampoline =
    `\n    var __module = ${wrap(parserSource)};\n` +
    `    globalThis.__crossnoteCallHook = function (hookName, input) {\n` +
    `      var hook = __module && typeof __module[hookName] === 'function'\n` +
    `        ? __module[hookName] : null;\n` +
    `      if (!hook) return Promise.resolve(input);\n` +
    `      return Promise.resolve(hook(input)).then(function (result) {\n` +
    `        return String(result);\n` +
    `      });\n` +
    `    };\n`;

  t = now();
  deadline = Date.now() + deadlineMs;
  const evalRes = ctx.evalCode(trampoline);
  if (evalRes.error) {
    const e = ctx.dump(evalRes.error);
    evalRes.error.dispose();
    throw new Error("parser eval failed: " + (e && e.message ? e.message : e));
  }
  evalRes.value.dispose();
  timings.evalMs = now() - t;
  const hookFn = ctx.getProp(ctx.global, "__crossnoteCallHook");

  const dumpErr = (h) => {
    const e = ctx.dump(h);
    return new Error(e && e.message ? `${e.name || "Error"}: ${e.message}` : String(e));
  };

  // Returns {output, marshalInMs, callMs, marshalOutMs, totalMs}
  async function callHook(name, input) {
    deadline = Date.now() + deadlineMs;
    const t0 = now();
    const hName = ctx.newString(name);
    const hIn = ctx.newString(input);
    const t1 = now();
    const res = ctx.callFunction(hookFn, ctx.undefined, [hName, hIn]);
    hName.dispose();
    hIn.dispose();
    if (res.error) {
      const e = dumpErr(res.error);
      res.error.dispose();
      throw e;
    }
    const settledP = ctx.resolvePromise(res.value);
    res.value.dispose();
    rt.executePendingJobs();
    const settled = await settledP;
    const t2 = now();
    if (settled.error) {
      const e = dumpErr(settled.error);
      settled.error.dispose();
      throw e;
    }
    const out = ctx.dump(settled.value);
    settled.value.dispose();
    const t3 = now();
    return {
      output: out,
      marshalInMs: t1 - t0,
      callMs: t2 - t1,
      marshalOutMs: t3 - t2,
      totalMs: t3 - t0,
    };
  }

  function dispose() {
    hookFn.dispose();
    ctx.dispose();
    rt.dispose();
  }
  return { callHook, timings, dispose };
}

// -------------------------------------------------------------- timing ----
function stats(times) {
  const s = times.slice().sort((a, b) => a - b);
  const sum = times.reduce((a, b) => a + b, 0);
  return {
    min: s[0],
    med: s[Math.floor(s.length / 2)],
    mean: sum / times.length,
  };
}

// ----------------------------------------------------------------- main ----
async function main() {
  const parserSource = fs.readFileSync(PARSER_PATH, "utf8");
  const markdownIt = resolveDep("markdown-it");
  const qjsCore = resolveDep("quickjs-emscripten-core");
  const qjsVariant = resolveDep("@jitl/quickjs-singlefile-cjs-release-sync");
  const crossnote = resolveDep("crossnote");

  const corpus = [];
  if (corpusOverride) {
    for (const p of corpusOverride)
      corpus.push([path.basename(p), path.resolve(p)]);
  } else {
    corpus.push(...DEFAULT_CORPUS);
    const synPath = path.join(
      require("node:os").tmpdir(),
      "crossnote-bench-synthetic.md",
    );
    fs.writeFileSync(synPath, genSynthetic(opt.syntheticLines, 20));
    corpus.push(["synthetic-3k", synPath]);
  }

  // Vault files come and go (renames, machine-specific vaults) — a missing
  // corpus entry must not kill the whole bench.
  const docs = corpus
    .filter(([name, p]) => {
      if (fs.existsSync(p)) return true;
      console.error(`!! corpus file missing, skipping: ${name} (${p})`);
      return false;
    })
    .map(([name, p]) => {
    const markdown = fs.readFileSync(p, "utf8");
    return {
      name,
      path: p,
      markdown,
      lines: markdown.split("\n").length,
      pseudoFences: (markdown.match(/^[ \t]{0,3}`{3,}pseudocode\b/gm) || [])
        .length,
    };
  });

  // ---- Phase A: clean notebook (identity parser) — baseline parseMD and the
  // REAL pre-hook HTML for onDidParseMarkdown input.
  let cleanHtml = null;
  let baseline = null;
  if (opt.e2e && crossnote) {
    cleanHtml = {};
    baseline = {};
    try {
      const proj = fs.mkdtempSync("/tmp/crossnote-bench-clean-");
      const t0 = now();
      // NOTE: config is spread LAST over the loaded .crossnote config inside
      // Notebook.init — passing getDefaultNotebookConfig() would clobber the
      // loaded parserConfig with identity hooks. Only override what we need.
      const nb = await crossnote.Notebook.init({
        notebookPath: proj,
        config: {
          wikiLinkResolution: "shortest",
          mathRenderingOption: "KaTeX",
          previewTheme: "none.css",
        },
      });
      baseline.notebookInitMs = now() - t0;
      // Warm the shared V8 code paths once so the first timed doc doesn't
      // carry the JIT/transform cold-start penalty.
      try {
        const w =
          nb.getNoteMarkdownEngine(docs[0].path) ??
          (await nb.getMarkdownEngine?.(docs[0].path));
        await w.parseMD("# warmup\n\n```pseudocode\nx\n```\n", {
          isForPreview: true,
          useRelativeFilePath: false,
          hideFrontMatter: false,
        });
      } catch {
        /* warmup is best-effort */
      }
      for (const d of docs) {
        try {
          const engine =
            nb.getNoteMarkdownEngine(d.path) ??
            (await nb.getMarkdownEngine?.(d.path));
          const t = now();
          const out = await engine.parseMD(d.markdown, {
            isForPreview: true,
            useRelativeFilePath: false,
            hideFrontMatter: false,
          });
          const html = typeof out === "string" ? out : out.html || "";
          baseline[d.name] = { parseMdMs: now() - t, htmlBytes: html.length };
          cleanHtml[d.name] = html;
        } catch (e) {
          baseline[d.name] = { error: String((e && e.message) || e) };
          cleanHtml[d.name] = null;
        }
      }
    } catch (e) {
      baseline = { error: String((e && e.stack) || e) };
      cleanHtml = null;
    }
  }

  const renderHtml = makeHtmlRenderer(markdownIt);
  for (const d of docs) {
    d.html = (cleanHtml && cleanHtml[d.name]) || renderHtml(d.markdown);
    d.htmlIsReal = !!(cleanHtml && cleanHtml[d.name]);
    d.htmlBytes = d.html.length;
  }

  // ---- init costs ----
  const nodeInit = loadParserNode(parserSource);
  const report = {
    init: {
      nodeEvalMs: nodeInit.initMs,
      parserKB: parserSource.length / 1024,
    },
    baseline,
    docs: [],
  };

  let qjs = null;
  let echo = null;
  if (qjsCore && qjsVariant) {
    const tw = now();
    const qjsMod = await qjsCore.newQuickJSWASMModuleFromVariant(
      qjsVariant.default || qjsVariant,
    );
    report.init.qjsWasmModuleMs = now() - tw;
    qjs = await loadParserQuickJS(qjsMod, parserSource, opt.deadline);
    report.init.qjsContextMs = qjs.timings.contextMs;
    report.init.qjsEvalMs = qjs.timings.evalMs;

    // Marshal-only baseline: identity hooks, same boundary.
    echo = await loadParserQuickJS(
      qjsMod,
      "({ onWillParseMarkdown: async s => s, onDidParseMarkdown: async s => s })",
      opt.deadline,
    );
  } else {
    console.error("!! quickjs-emscripten-core not resolvable — skipping sandbox path");
  }

  // ---- per-doc timings ----
  for (const d of docs) {
    const row = {
      name: d.name,
      bytes: d.markdown.length,
      lines: d.lines,
      pseudoFences: d.pseudoFences,
      htmlBytes: d.htmlBytes,
      htmlIsReal: d.htmlIsReal,
    };

    // Node vm path
    const willN = [],
      didN = [];
    for (let i = 0; i < opt.repeat; i++) {
      let t = now();
      await nodeInit.parser.onWillParseMarkdown(d.markdown);
      willN.push(now() - t);
      t = now();
      await nodeInit.parser.onDidParseMarkdown(d.html);
      didN.push(now() - t);
    }
    row.node = { will: stats(willN), did: stats(didN) };

    // QuickJS path — call[0] is cold (figureCache empty for this doc),
    // later calls measure warm/memoized behavior.
    if (qjs) {
      const calls = [];
      for (let i = 0; i < opt.repeat; i++) {
        const w = await qjs.callHook("onWillParseMarkdown", d.markdown);
        const did = await qjs.callHook("onDidParseMarkdown", d.html);
        calls.push({ w, did });
      }
      const pick = (k, f, arr) => stats((arr || calls).map((c) => c[k][f]));
      const warm = calls.slice(1).length ? calls.slice(1) : calls;
      row.qjs = {
        will: stats(calls.map((c) => c.w.totalMs)),
        did: stats(calls.map((c) => c.did.totalMs)),
        didCold: calls[0].did.totalMs,
        didColdCall: calls[0].did.callMs,
        willMarshalIn: pick("w", "marshalInMs"),
        willCall: pick("w", "callMs"),
        willMarshalOut: pick("w", "marshalOutMs"),
        didMarshalIn: pick("did", "marshalInMs"),
        didCall: pick("did", "callMs"),
        didMarshalOut: pick("did", "marshalOutMs"),
        didWarmCall: pick("did", "callMs", warm),
      };
      if (echo) {
        const e1 = await echo.callHook("onWillParseMarkdown", d.markdown);
        const e2 = await echo.callHook("onDidParseMarkdown", d.html);
        row.qjs.echoWillMs = e1.totalMs;
        row.qjs.echoDidMs = e2.totalMs;
      }
    }
    report.docs.push(row);
  }
  if (echo) echo.dispose();

  // ---- Phase C: farm notebook (.crossnote symlinked) — real hooks, e2e ----
  if (opt.e2e && crossnote) {
    try {
      const proj = fs.mkdtempSync("/tmp/crossnote-bench-farm-");
      fs.symlinkSync(CROSSNOTE_DIR, path.join(proj, ".crossnote"), "dir");
      const t0 = now();
      const nb = await crossnote.Notebook.init({
        notebookPath: proj,
        config: {
          wikiLinkResolution: "shortest",
          mathRenderingOption: "KaTeX",
          previewTheme: "none.css",
        },
      });
      report.e2e = { notebookInitMs: now() - t0, docs: {} };
      try {
        const w =
          nb.getNoteMarkdownEngine(docs[0].path) ??
          (await nb.getMarkdownEngine?.(docs[0].path));
        await w.parseMD("# warmup\n\n```pseudocode\nx\n```\n", {
          isForPreview: true,
          useRelativeFilePath: false,
          hideFrontMatter: false,
        });
      } catch {
        /* warmup is best-effort */
      }
      for (const d of docs) {
        try {
          const engine =
            nb.getNoteMarkdownEngine(d.path) ??
            (await nb.getMarkdownEngine?.(d.path));
          const t = now();
          const out = await engine.parseMD(d.markdown, {
            isForPreview: true,
            useRelativeFilePath: false,
            hideFrontMatter: false,
          });
          const el = now() - t;
          const html = typeof out === "string" ? out : out.html || "";
          const md2 = typeof out === "object" && out.markdown ? out.markdown : "";
          report.e2e.docs[d.name] = {
            parseMdMs: el,
            htmlBytes: html.length,
            figureRendered: html.includes("crossnote-pseudocode"),
            themeImported:
              md2.includes("crossnote-theme-toggle") ||
              (out.JSAndCssFiles || []).some((f) => f.includes("theme-toggle")),
          };
        } catch (e) {
          report.e2e.docs[d.name] = { error: String((e && e.message) || e) };
        }
      }
    } catch (e) {
      report.e2e = { error: String((e && e.stack) || e) };
    }
  }

  if (qjs) qjs.dispose();

  // ---- print ----
  if (opt.json) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  console.log(`\n## init (one-time per notebook)`);
  console.log(`parser.js ${kb(parserSource.length)}`);
  console.log(`  node vm eval          ${fmt(report.init.nodeEvalMs)} ms`);
  if (report.init.qjsEvalMs !== undefined) {
    console.log(`  qjs wasm module load  ${fmt(report.init.qjsWasmModuleMs)} ms`);
    console.log(`  qjs runtime+context   ${fmt(report.init.qjsContextMs)} ms`);
    console.log(`  qjs evalCode(parser)  ${fmt(report.init.qjsEvalMs)} ms`);
  }

  console.log(
    `\n## per-render hook timings (median of ${opt.repeat}; did input = ${report.docs.some((d) => d.htmlIsReal) ? "real crossnote HTML" : "markdown-it HTML"})`,
  );
  console.log(
    "| doc | md size | html size | pseudo | onWill node | onWill qjs | onDid node | onDid qjs | echo will | echo did |",
  );
  console.log(
    "| --- | ------- | --------- | ------ | ----------- | ---------- | ---------- | --------- | -------- | -------- |",
  );
  for (const r of report.docs) {
    const q = r.qjs || {};
    console.log(
      `| ${r.name} | ${kb(r.bytes)} | ${kb(r.htmlBytes)} | ${r.pseudoFences} | ` +
        `${fmt(r.node.will.med)} ms | ${q.will ? fmt(q.will.med) + " ms" : "-"} | ` +
        `${fmt(r.node.did.med)} ms | ${q.did ? fmt(q.did.med) + " ms" : "-"} | ` +
        `${q.echoWillMs !== undefined ? fmt(q.echoWillMs) + " ms" : "-"} | ` +
        `${q.echoDidMs !== undefined ? fmt(q.echoDidMs) + " ms" : "-"} |`,
    );
  }

  if (report.docs.some((r) => r.qjs)) {
    console.log(
      `\n## qjs breakdown (median): marshalIn / interpreted call / marshalOut — cold = first render`,
    );
    console.log(
      "| doc | will in | will call | will out | did in | did cold | did warm | did out |",
    );
    console.log(
      "| --- | ------- | --------- | -------- | ------ | -------- | -------- | ------- |",
    );
    for (const r of report.docs) {
      const q = r.qjs;
      if (!q) continue;
      console.log(
        `| ${r.name} | ${fmt(q.willMarshalIn.med)} | ${fmt(q.willCall.med)} | ${fmt(q.willMarshalOut.med)} | ` +
          `${fmt(q.didMarshalIn.med)} | ${fmt(q.didColdCall)} | ${fmt(q.didWarmCall.med)} | ${fmt(q.didMarshalOut.med)} |`,
      );
    }
    console.log(
      `\nProduction deadline per hook call: ${PROD_HOOK_DEADLINE_MS} ms — any cell above it kills the preview render.`,
    );
  }

  if (baseline && !baseline.error) {
    console.log(`\n## baseline parseMD (identity hooks — full pipeline, no logic)`);
    console.log(`notebook init ${fmt(baseline.notebookInitMs)} ms`);
    for (const d of report.docs) {
      const b = baseline[d.name];
      console.log(
        `  ${d.name}: ${b && b.error ? "ERROR " + b.error : fmt(b.parseMdMs) + " ms → " + kb(b.htmlBytes) + " html"}`,
      );
    }
  } else if (baseline && baseline.error) {
    console.log("\n## baseline parseMD failed:", baseline.error);
  }

  if (report.e2e) {
    console.log(`\n## end-to-end parseMD with real parser.js`);
    if (report.e2e.error) console.log("e2e failed:", report.e2e.error);
    else {
      console.log(`notebook init ${fmt(report.e2e.notebookInitMs)} ms`);
      for (const [name, r] of Object.entries(report.e2e.docs)) {
        console.log(
          `  ${name}: ${
            r.error
              ? "ERROR " + r.error
              : fmt(r.parseMdMs) + " ms → " + kb(r.htmlBytes) + " html" +
                (r.figureRendered ? " (figure rendered)" : "") +
                (r.themeImported ? "" : " [no import markers!]")
          }`,
        );
      }
    }
  }
}

main().catch((e) => {
  console.error("FATAL:", (e && e.stack) || e);
  process.exit(1);
});
