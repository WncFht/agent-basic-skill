#!/usr/bin/env node
// Lint every pseudocode fenced block in the repo containing cwd
// (``` / ~~~ / 4+-backtick fences, per CommonMark).
//
// Usage:
//   node .crossnote/scripts/check-pseudocode.cjs            # sweep all tracked .md
//   node .crossnote/scripts/check-pseudocode.cjs --staged   # staged .md only (git index)
//   node .crossnote/scripts/check-pseudocode.cjs FILE ...   # explicit files, resolved vs cwd
//
// A block fails when pseudocode.js (plus the runtime's \textcolor preprocessing)
// rejects it — that is exactly what the MPE preview does, so failures here are
// guaranteed to break preview rendering. Missing caption `Semantics:` markers
// are reported as warnings and never fail the run.
//
// Exit code: 0 = clean (or warnings only), 1 = at least one parse failure.

"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

// This script reaches each repo through a .crossnote/scripts directory
// symlink — node realpaths the main module, so __dirname lands inside the
// canonical source (~/.agents/...) no matter which repo invoked it. The lint
// target must therefore come from the invocation context, not the script
// location: the git repo containing cwd (git hooks always run from the
// toplevel), or cwd itself outside any repo.
const VAULT_ROOT = (() => {
  try {
    return execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd: process.cwd(),
      encoding: "utf8",
    }).trim();
  } catch {
    return process.cwd();
  }
})();
const CROSSNOTE_DIR = path.join(__dirname, "..");

// pseudocode.js discovers the math backend via the `katex` global (browser:
// window.katex), and the shared renderFigureToHtml resolves `pseudocode` the
// same way. Expose the vendored builds on globalThis before requiring the
// runtime.
globalThis.katex = require(path.join(
  CROSSNOTE_DIR,
  "vendor",
  "katex-0.16.47.min.js",
));
globalThis.pseudocode = require(path.join(
  CROSSNOTE_DIR,
  "vendor",
  "pseudocode-2.4.1.min.js",
));
const runtime = require(path.join(CROSSNOTE_DIR, "pseudocode-runtime.js"));

// CommonMark fence scan — line-based open/close tracking mirroring
// parser.js's FENCE_LINE/eachFenceOpen so lint coverage equals what the
// preview renders:
//   * 3+ backticks/tildes/colons, ≤3 leading SPACES (a leading tab is already
//     column 4 = indented code, never a fence);
//   * any mix of container prefixes (blockquote `>` + ≤1 space, list markers —
//     containers strip indentation, so list-nested fences still render);
//   * an open fence swallows inner-looking markers (shorter runs or a
//     different marker char are body text — a ````markdown example containing
//     a ```pseudocode block is intentionally not linted);
//   * a closing fence needs the same marker char, a run ≥ the opener's, and
//     an empty info string (a longer closing run is legal CommonMark);
//   * an unclosed opener renders to end of document — it is linted too, so a
//     mid-edit save that deleted the closing line cannot slip past the gate.
const FENCE_LINE =
  /^([ ]{0,3})((?:(?:>[ \t]?|[-+*][ \t]+|\d{1,9}[.)][ \t]+))*)([ ]{0,3})(`{3,}|~{3,}|:{3,})([^\n]*)$/;
const CONTAINER_GROUP = />[ \t]?|[-+*][ \t]+|\d{1,9}[.)][ \t]+/g;
const LIST_GROUP = /^[-+*]|^\d{1,9}[.)]/;
const PSEUDOCODE_LANG_RE = /^pseudocode(?=[\s{]|$)/i;
// \caption must carry a Semantics marker naming the provenance — inside the
// caption braces, so a stray `Semantics:` elsewhere in the block cannot pass.
// The canonical values are 论文原文忠实 / 官方实现忠实 / 根据正文重构;
// descriptive refinements (e.g. 根据论文 Algorithm 3 重构) are also accepted.
const SEMANTICS_RE = /Semantics:\s*\S/;

// Strips the fence's container prefixes from a body line, per container:
//   * blockquote — exactly one `>` level per line; `> >foo` at depth 1 keeps
//     the inner `>` (the renderer strips one level too), and a line without
//     `>` is a lazy continuation that keeps its text;
//   * list — the item marker can't reappear mid-fence (a same-level item
//     would end the fence, not nest inside it), so only the continuation
//     indent is stripped: up to the open-line marker's width of leading
//     spaces. An explicit `- `/`>` on a body line is literal content.
// After containers, CommonMark's own fence rule applies: body lines lose up
// to `indent` leading spaces — the opener's own indent.
function stripContainerDepth(line, containers, indent) {
  let s = line;
  for (const c of containers) {
    const ws = /^[ ]{0,3}/.exec(s)[0];
    const rest = s.slice(ws.length);
    if (c.list) {
      s = s.slice(Math.min(ws.length, c.width));
    } else {
      const q = /^>[ \t]?/.exec(rest);
      if (q) s = rest.slice(q[0].length);
    }
  }
  if (indent > 0) {
    const ws = /^[ ]*/.exec(s)[0];
    s = s.slice(Math.min(ws.length, indent));
  }
  return s;
}

function* iterPseudocodeBlocks(text) {
  const lines = text.split("\n");
  let open = null;
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    const match = FENCE_LINE.exec(line);
    if (open) {
      if (
        match &&
        match[4][0] === open.char &&
        match[4].length >= open.len &&
        match[5].trim() === ""
      ) {
        if (PSEUDOCODE_LANG_RE.test(open.info)) {
          yield {
            info: open.info,
            source: open.body.join("\n"),
            line: open.startLine,
          };
        }
        open = null;
      } else {
        open.body.push(
          stripContainerDepth(line, open.containers, open.indent),
        );
      }
      continue;
    }
    if (!match) continue;
    const marker = match[4];
    const info = match[5];
    // A backtick opener whose info contains ` is not a legal CommonMark
    // fence — the line renders as a paragraph instead.
    if (marker[0] === "`" && info.includes("`")) continue;
    CONTAINER_GROUP.lastIndex = 0;
    const groups = match[2].match(CONTAINER_GROUP) || [];
    open = {
      char: marker[0],
      len: marker.length,
      containers: groups.map((g) => ({
        list: LIST_GROUP.test(g),
        width: g.length,
      })),
      // Body lines lose up to the opener's indent (CommonMark fence rule).
      // With containers the relevant indent is the run inside the innermost
      // one; without, both runs are the fence's own indentation.
      indent:
        groups.length > 0
          ? match[3].length
          : match[1].length + match[3].length,
      info: info.trim(),
      startLine: i + 1,
      body: [],
    };
  }
  // Unclosed fence at EOF: CommonMark renders the body to end of document.
  if (open && PSEUDOCODE_LANG_RE.test(open.info)) {
    yield { info: open.info, source: open.body.join("\n"), line: open.startLine };
  }
}

// pseudocode.js parser errors embed a character offset ("at position N");
// map it to a 0-based line delta within the block so diagnostics can point at
// the offending line instead of the fence's first line.
function errorLineDelta(source, message) {
  const match = /at position (\d+)/.exec(message || "");
  if (!match) return 0;
  const position = Math.min(Number(match[1]), source.length);
  return source.slice(0, position).split("\n").length - 1;
}

// Returns {errors: [{message, lineDelta}], warnings: [message]}.
function checkBlock(source, info) {
  const errors = [];
  const warnings = [];
  try {
    // Full pipeline parity with the preview and export prerender: color
    // preprocessing, option parsing, renderToString, marker re-materialization,
    // figure wrapping — all inside renderFigureToHtml.
    runtime.renderFigureToHtml(source, info, 0, null);
  } catch (error) {
    const message = error.message || String(error);
    errors.push({ message, lineDelta: errorLineDelta(source, message) });
  }
  const caption = runtime.extractCaptionBody(source);
  if (caption === null || !SEMANTICS_RE.test(caption)) {
    warnings.push(
      "\\caption missing `Semantics:` marker (论文原文忠实|官方实现忠实|根据正文重构)",
    );
  }
  // Info-string hygiene: invalid option values and typos (e.g. `nubmered`,
  // `indent=2px`) are ignored by the renderer — surface them as warnings.
  for (const message of runtime.collectRenderOptionWarnings(info)) {
    warnings.push("info: " + message);
  }
  return { errors, warnings };
}

function lintText(fileLabel, text) {
  const problems = [];
  let blockCount = 0;
  for (const block of iterPseudocodeBlocks(text)) {
    blockCount += 1;
    const { errors, warnings } = checkBlock(block.source, block.info);
    for (const entry of errors) {
      problems.push({
        severity: "error",
        line: block.line + 1 + entry.lineDelta,
        message: entry.message,
      });
    }
    for (const message of warnings) {
      problems.push({ severity: "warning", line: block.line, message });
    }
  }
  return {
    problems: problems.map((p) => ({ file: fileLabel, ...p })),
    blockCount,
  };
}

function gitListFiles(args) {
  const out = execFileSync("git", args, {
    cwd: VAULT_ROOT,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return out.split("\0").filter(Boolean);
}

function collectStaged() {
  // [relative path, staged content]
  const files = gitListFiles([
    "diff",
    "--cached",
    "--diff-filter=ACMR",
    "--name-only",
    "-z",
    "--",
    "*.md",
  ]);
  const entries = [];
  for (const rel of files) {
    let content;
    try {
      content = execFileSync("git", ["show", `:${rel}`], {
        cwd: VAULT_ROOT,
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
      });
    } catch {
      continue; // submodule / unreadable stage entry — nothing to lint
    }
    entries.push([rel, content]);
  }
  return entries;
}

function collectTracked() {
  const entries = [];
  for (const rel of gitListFiles(["ls-files", "-z", "--", "*.md"])) {
    const abs = path.join(VAULT_ROOT, rel);
    // ls-files still lists paths deleted from the working tree.
    if (!fs.existsSync(abs)) continue;
    entries.push([rel, fs.readFileSync(abs, "utf8")]);
  }
  return entries;
}

function collectExplicit(files) {
  const entries = [];
  for (const file of files) {
    const abs = path.resolve(process.cwd(), file);
    const rel = path.relative(VAULT_ROOT, abs);
    // Label repo-relative when the file is inside the linted repo, else the
    // absolute path (e.g. fixtures under os.tmpdir()).
    const label = rel === "" || rel.startsWith("..") || path.isAbsolute(rel) ? abs : rel;
    entries.push([label, fs.readFileSync(abs, "utf8")]);
  }
  return entries;
}

function main(argv) {
  // Partition flags from files up front: a misplaced --staged used to be
  // treated as a filename (ENOENT crash), and files after --staged were
  // silently dropped.
  const files = [];
  let staged = false;
  for (const arg of argv) {
    if (arg === "--staged") staged = true;
    else if (arg.startsWith("--")) {
      console.error(`check-pseudocode: unknown flag ${arg}`);
      return 2;
    } else files.push(arg);
  }
  if (staged && files.length) {
    console.error("check-pseudocode: --staged takes no file arguments");
    return 2;
  }

  let entries;
  if (staged) {
    entries = collectStaged();
  } else if (files.length) {
    entries = collectExplicit(files);
  } else {
    entries = collectTracked();
  }

  let errorCount = 0;
  let warningCount = 0;
  let blockCount = 0;

  for (const [rel, content] of entries) {
    const result = lintText(rel, content);
    blockCount += result.blockCount;
    for (const p of result.problems) {
      if (p.severity === "error") errorCount += 1;
      else warningCount += 1;
      console.log(`${p.file}:${p.line}: ${p.severity}: ${p.message}`);
    }
  }

  console.log(
    `check-pseudocode: ${blockCount} block(s) in ${entries.length} file(s), ` +
      `${errorCount} error(s), ${warningCount} warning(s)`,
  );
  return errorCount === 0 ? 0 : 1;
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
}

module.exports = {
  checkBlock,
  iterPseudocodeBlocks,
  lintText,
  VAULT_ROOT,
};
