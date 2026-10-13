"use strict";

// Unit tests for the pure helpers exported by pseudocode-runtime.js for Node
// consumers (lint script + tests). No browser required.

const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const runtime = require(path.join(__dirname, "..", "pseudocode-runtime.js"));

test("parseRenderOptions returns defaults for a bare pseudocode fence", () => {
  const o = runtime.parseRenderOptions("pseudocode");
  assert.equal(o.lineNumber, false);
  assert.equal(o.noEnd, false);
  assert.equal(o.scopeLines, false);
  assert.equal(o.titlePrefix, "Algorithm");
  assert.equal(o.indentSize, "1.2em");
});

test("parseRenderOptions handles missing/empty info", () => {
  for (const info of ["", undefined, null]) {
    const o = runtime.parseRenderOptions(info);
    assert.equal(o.titlePrefix, "Algorithm");
  }
});

test("numbered / linenum enable line numbers", () => {
  for (const info of ["pseudocode numbered", "pseudocode linenum"]) {
    assert.equal(runtime.parseRenderOptions(info).lineNumber, true);
  }
});

test("noend and scopelines flags", () => {
  const o = runtime.parseRenderOptions("pseudocode noend scopelines");
  assert.equal(o.noEnd, true);
  assert.equal(o.scopeLines, true);
});

test("title and indent key=value options", () => {
  const o = runtime.parseRenderOptions("pseudocode title=算法 indent=1.5em");
  assert.equal(o.titlePrefix, "算法");
  assert.equal(o.indentSize, "1.5em");
  assert.equal(o.lineNumber, false);
});

test("linepunc and commentdelim key=value options", () => {
  const o = runtime.parseRenderOptions(
    "pseudocode numbered linepunc=. commentdelim=▷",
  );
  assert.equal(o.lineNumber, true);
  assert.equal(o.lineNumberPunc, ".");
  assert.equal(o.commentDelimiter, "▷");
});

test("linepunc/commentdelim reject spaces, braces and backslashes", () => {
  for (const info of [
    "pseudocode linepunc={.}",
    "pseudocode linepunc=toolongvalue",
    "pseudocode commentdelim=a\\\\b",
  ]) {
    const o = runtime.parseRenderOptions(info);
    assert.equal(o.lineNumberPunc, undefined);
    assert.equal(o.commentDelimiter, undefined);
  }
});

test("bare flag words inside {...} attrs still apply", () => {
  // crossnote treats {numbered} as an attribute — honor the obvious intent
  assert.equal(
    runtime.parseRenderOptions("pseudocode {numbered} {.cls #id}").lineNumber,
    true,
  );
  // .class / #id / k=v inside braces are crossnote's, not ours
  assert.equal(
    runtime.parseRenderOptions("pseudocode {.numbered} {#linenum}").lineNumber,
    false,
  );
});

test("unknown tokens and invalid values are ignored", () => {
  const o = runtime.parseRenderOptions("pseudocode bogus indent=abc x=1");
  assert.equal(o.indentSize, "1.2em");
  assert.equal(o.titlePrefix, "Algorithm");
});

test("collectRenderOptionWarnings stays quiet for valid info strings", () => {
  for (const info of [
    "pseudocode",
    "pseudocode numbered noend scopelines title=算法 indent=1.5em linepunc=. commentdelim=▷",
    "pseudocode {.extra #id data-source-line=3}", // crossnote attr syntax
    "pseudocode numbered {.cls}",
    "",
  ]) {
    assert.deepEqual(runtime.collectRenderOptionWarnings(info), [], info);
  }
});

test("collectRenderOptionWarnings flags typos, bad values, unknown options", () => {
  assert.deepEqual(
    runtime.collectRenderOptionWarnings("pseudocode nubmered"),
    ["unknown flag 'nubmered' — known: numbered, linenum, noend, scopelines"],
  );
  assert.deepEqual(
    runtime.collectRenderOptionWarnings("pseudocode indent=2px"),
    ["indent=2px ignored — only em units (e.g. indent=1.5em)"],
  );
  assert.deepEqual(
    runtime.collectRenderOptionWarnings("pseudocode size=big"),
    ["unknown option 'size=' — known: title, indent, linepunc, commentdelim"],
  );
  assert.match(
    runtime.collectRenderOptionWarnings("pseudocode linepunc=toolong")[0],
    /linepunc=toolong ignored/,
  );
});

test("preprocessTextColors rewrites text-mode \\textcolor into markers", () => {
  const markers = [];
  const out = runtime.preprocessTextColors(
    "\\STATE \\textcolor{red}{boom} and $x$",
    markers,
    "PFX",
  );
  assert.equal(markers.length, 1);
  assert.equal(markers[0].color, "red");
  assert.match(out, /PFXOPEN0TOKENboomPFXCLOSE0TOKEN/);
});

test("preprocessTextColors leaves math-mode \\textcolor to KaTeX", () => {
  const markers = [];
  const out = runtime.preprocessTextColors(
    "\\STATE $\\textcolor{red}{x} + 1$",
    markers,
    "PFX",
  );
  assert.equal(markers.length, 0);
  assert.equal(out, "\\STATE $\\textcolor{red}{x} + 1$");
});

test("preprocessTextColors rejects colors outside the palette", () => {
  assert.throws(
    () =>
      runtime.preprocessTextColors(
        "\\STATE \\textcolor{magenta}{x}",
        [],
        "PFX",
      ),
    /Unsupported text color/,
  );
});
