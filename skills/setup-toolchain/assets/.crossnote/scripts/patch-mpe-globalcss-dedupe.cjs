#!/usr/bin/env node
"use strict";

// Patches MPE's bundled extension.js and crossnote-serve.js (the serve CLI
// spawned for crossnoteServePort carries the same sites) to stop emitting the
// combined globalCss twice per generated document:
//
//   1. global/workspace style.less contents are byte-identical in the farmed
//      setup (both resolve to the canonical file), but the config merge emits
//      `global + workspace` unconditionally — the dedupe keeps the concat
//      semantics while emitting one copy when they match.
//   2. The same ~120KB string is also serialized into <meta data-config> even
//      though the webview only lists it as a useEffect dep and never reads the
//      value — `globalCss:void 0` drops it from the JSON.
//
//   node .crossnote/scripts/patch-mpe-globalcss-dedupe.cjs [extension.js ...]
//
// Idempotent — re-running reports sites as already patched. A sibling
// `*.crossnote-bak` backup is written before the first modification.

const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

// VS Code keeps stale versioned extension dirs after each MPE update — a
// hardcoded version patches a dormant bundle while the active one regresses
// silently. Discover every installed build under both roots; the patch is
// idempotent so touching dormant copies is harmless.
function defaultTargets() {
  const targets = [];
  for (const root of [
    path.join(require("node:os").homedir(), ".vscode", "extensions"),
    path.join(require("node:os").homedir(), ".vscode-server", "extensions"),
  ]) {
    let entries;
    try {
      entries = fs.readdirSync(root, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (
        entry.isDirectory() &&
        entry.name.startsWith("shd101wyy.markdown-preview-enhanced-")
      ) {
        for (const bundle of ["extension.js", "crossnote-serve.js"]) {
          const candidate = path.join(
            root,
            entry.name,
            "out",
            "native",
            bundle,
          );
          if (fs.existsSync(candidate)) targets.push(candidate);
        }
      }
    }
  }
  return targets.sort();
}

// globalCss:(X.globalCss??"")+(Y.globalCss??"")  ->  dedupe ternary
const CONCAT_RE =
  /globalCss:\(([A-Za-z_$][\w$]*)\.globalCss\?\?""\)\+\(([A-Za-z_$][\w$]*)\.globalCss\?\?""\)/g;
// JSON.stringify({...this.notebook.config,...X})  ->  strip globalCss key
// (the second spread's minified name differs per bundle: s in extension.js,
// o in crossnote-serve.js)
const DATA_CONFIG_RE =
  /JSON\.stringify\(\{\.\.\.this\.notebook\.config,\.\.\.([A-Za-z_$][\w$]*)\}\)/g;

function dedupeReplacement(_, globalVar, workspaceVar) {
  const g = `(${globalVar}.globalCss??"")`;
  const w = `(${workspaceVar}.globalCss??"")`;
  return `globalCss:${g}===${w}?${g}:${g}+${w}`;
}

function patchSource(source) {
  let concatHits = 0;
  let configHits = 0;
  const next = source
    .replace(CONCAT_RE, (...args) => {
      concatHits += 1;
      return dedupeReplacement(...args);
    })
    .replace(DATA_CONFIG_RE, (_, configVar) => {
      configHits += 1;
      return `JSON.stringify({...this.notebook.config,...${configVar},globalCss:void 0})`;
    });
  return { next, concatHits, configHits };
}

// Returns "patched" | "already" | "no-match". "no-match" means neither regex
// found a site on a bundle that carries no patch marker — almost always a
// minifier/layout change in a newer MPE build, i.e. this script went stale.
function patchFile(file) {
  const source = fs.readFileSync(file, "utf8");
  const { next, concatHits, configHits } = patchSource(source);

  if (next === source) {
    if (
      source.includes("globalCss:void 0") ||
      /globalCss:\([A-Za-z_$][\w$]*\.globalCss\?\?""\)===\(/.test(source)
    ) {
      console.log(`${file}: already patched`);
      return "already";
    }
    console.error(
      `${file}: no matching sites — bundle layout changed? ` +
        "patch patterns need an update.",
    );
    return "no-match";
  }

  const tmp = `${file}.crossnote-tmp.js`;
  fs.writeFileSync(tmp, next);
  try {
    execFileSync(process.execPath, ["--check", tmp], { stdio: "pipe" });
  } catch (error) {
    fs.unlinkSync(tmp);
    throw new Error(`patched ${file} failed node --check: ${error.message}`);
  }

  const backup = `${file}.crossnote-bak`;
  if (!fs.existsSync(backup)) fs.copyFileSync(file, backup);
  fs.renameSync(tmp, file);
  console.log(
    `${file}: patched ${concatHits} concat site(s), ${configHits} data-config site(s) ` +
      `(${source.length} -> ${next.length} bytes; backup at ${backup})`,
  );
  // Partial application means one pattern matched and the other didn't —
  // same "bundle drifted" signal as no-match, just half-masked.
  if (concatHits === 0 || configHits === 0) {
    console.error(
      `${file}: warning — only one patch kind matched ` +
        `(concat=${concatHits}, data-config=${configHits}); ` +
        "the other pattern may need an update.",
    );
  }
  return "patched";
}

function main() {
  const args = process.argv.slice(2);
  const targets = args.length > 0 ? args : defaultTargets();
  if (targets.length === 0) {
    console.error("No extension.js found — pass the bundle path explicitly.");
    process.exitCode = 1;
    return;
  }
  let unmatched = 0;
  for (const file of targets) {
    if (patchFile(file) === "no-match") unmatched += 1;
  }
  // Exit 2 when any live bundle matched nothing — distinct from the no-files
  // exit 1 so automation can tell "script went stale" from "nothing to do".
  if (unmatched > 0) process.exitCode = 2;
}

main();
