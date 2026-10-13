#!/usr/bin/env node
"use strict";

// Regenerates the GENERATED section of .crossnote/parser.js.
//
// Since crossnote 0.9.30, parser.js is evaluated as a single expression inside
// a QuickJS WASM sandbox — no require/fs/window. To render ```pseudocode blocks
// during onDidParseMarkdown (which also covers HTML/print exports), the
// vendored KaTeX + pseudocode.js builds are inlined as JSON string constants
// that parser.js eval's lazily on first use (the ~300KB compile is only paid
// by notebooks that actually contain pseudocode), while the DOM-free
// "PURE CORE" slice of pseudocode-runtime.js is inlined as plain code.
//
//   node .crossnote/scripts/build-parser.cjs          # rewrite parser.js
//   node .crossnote/scripts/build-parser.cjs --check  # exit 1 if stale
//
// Re-run this whenever vendor/* or the PURE CORE slice of
// pseudocode-runtime.js changes. The parser-build test runs --check.

const fs = require("node:fs");
const path = require("node:path");

const CROSSNOTE = path.resolve(__dirname, "..");
const PARSER_PATH = path.join(CROSSNOTE, "parser.js");
const RUNTIME_PATH = path.join(CROSSNOTE, "pseudocode-runtime.js");
const KATEX_PATH = path.join(CROSSNOTE, "vendor", "katex-0.16.47.min.js");
const PSEUDOCODE_PATH = path.join(CROSSNOTE, "vendor", "pseudocode-2.4.1.min.js");

const GENERATED_BEGIN = "======== BEGIN GENERATED";
const GENERATED_END = "======== END GENERATED";
const CORE_BEGIN = "==== BEGIN PURE CORE ====";
const CORE_END = "==== END PURE CORE ====";

function sliceBetween(source, beginMarker, endMarker, label) {
  const begin = source.indexOf(beginMarker);
  // Search the end marker only after begin — a stray earlier occurrence must
  // not truncate the slice.
  const end = begin === -1 ? -1 : source.indexOf(endMarker, begin + beginMarker.length);
  if (begin === -1 || end === -1) {
    throw new Error(`Cannot find ${beginMarker} … ${endMarker} in ${label}`);
  }
  // Both markers sit inside `// …` comment lines: the slice runs from the
  // line after BEGIN to the line before END, so no comment prefix leaks in.
  const firstNewline = source.indexOf("\n", begin);
  const lastNewline = source.lastIndexOf("\n", end);
  if (firstNewline === -1 || lastNewline <= firstNewline) {
    throw new Error(`Malformed ${beginMarker} … ${endMarker} region in ${label}`);
  }
  return source.slice(firstNewline + 1, lastNewline + 1);
}

function generatedSection() {
  const katex = fs.readFileSync(KATEX_PATH, "utf8").trim();
  const pseudocode = fs.readFileSync(PSEUDOCODE_PATH, "utf8").trim();
  const runtime = fs.readFileSync(RUNTIME_PATH, "utf8");
  const core = sliceBetween(runtime, CORE_BEGIN, CORE_END, RUNTIME_PATH).trim();

  return [
    "//   [vendored katex-0.16.47.min.js — deferred eval, see ensureVendoredGlobals]",
    "var CROSSNOTE_KATEX_SRC = " + JSON.stringify(katex) + ";",
    "",
    "//   [vendored pseudocode-2.4.1.min.js — deferred eval]",
    "var CROSSNOTE_PSEUDOCODE_SRC = " + JSON.stringify(pseudocode) + ";",
    "",
    "//   [pure core of pseudocode-runtime.js — keep the markers in sync]",
    core,
    "",
  ].join("\n");
}

function build(source, generated) {
  const begin = source.indexOf(GENERATED_BEGIN);
  const end = source.indexOf(GENERATED_END);
  if (begin === -1 || end === -1 || end < begin) {
    throw new Error(
      `parser.js is missing its GENERATED markers (${GENERATED_BEGIN} / ${GENERATED_END})`,
    );
  }
  const beginLineEnd = source.indexOf("\n", begin);
  const endLineStart = source.lastIndexOf("\n", end);
  return {
    rebuilt:
      source.slice(0, beginLineEnd + 1) +
      generated +
      source.slice(endLineStart + 1),
    // The slice that will be replaced — compare against `generated` to tell
    // vendor drift from manual edits inside the markers.
    current: source.slice(beginLineEnd + 1, endLineStart + 1),
  };
}

function main() {
  const check = process.argv.includes("--check");
  const source = fs.readFileSync(PARSER_PATH, "utf8");
  const generated = generatedSection();
  const { rebuilt, current } = build(source, generated);

  if (check) {
    if (rebuilt === source) {
      console.log("parser.js GENERATED section is up to date.");
      return;
    }
    console.error(
      "parser.js GENERATED section is stale — run " +
        "`node .crossnote/scripts/build-parser.cjs`.",
    );
    process.exitCode = 1;
    return;
  }

  if (rebuilt === source) {
    console.log("parser.js already up to date.");
    return;
  }
  if (current !== generated) {
    console.warn(
      "note: existing GENERATED section differs from a fresh generation " +
        "(vendor update or a manual edit inside the markers) — overwriting it.",
    );
  }
  // Atomic replace: parser.js is the shared fact source every repo's
  // .crossnote/parser.js symlinks to — a torn write would truncate it for all
  // repos at once. node --check the candidate before it goes live.
  // Must keep a .js extension — `node --check` infers the module format
  // from the extension and rejects `.tmp`.
  const tmp = PARSER_PATH.replace(/\.js$/, ".tmp.js");
  fs.writeFileSync(tmp, rebuilt);
  const syntax = require("node:child_process").spawnSync(
    process.execPath,
    ["--check", tmp],
    { encoding: "utf8" },
  );
  if (syntax.status !== 0) {
    fs.unlinkSync(tmp);
    console.error(`parser.tmp.js failed node --check:\n${syntax.stderr}`);
    process.exitCode = 1;
    return;
  }
  fs.renameSync(tmp, PARSER_PATH);
  console.log(`parser.js regenerated (${rebuilt.length} bytes).`);
}

main();
