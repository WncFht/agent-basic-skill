"use strict";

// Guards against drift: parser.js embeds vendored builds and the PURE CORE
// slice of pseudocode-runtime.js. If either changes without regenerating,
// this fails — run `node .crossnote/scripts/build-parser.cjs`.

const { execFileSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

test("parser.js GENERATED section is in sync with its sources", () => {
  const script = path.resolve(__dirname, "..", "scripts", "build-parser.cjs");
  assert.doesNotThrow(() => execFileSync(process.execPath, [script, "--check"]));
});
