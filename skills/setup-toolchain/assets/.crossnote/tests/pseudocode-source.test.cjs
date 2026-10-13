"use strict";

// Vault-wide regression test: every ```pseudocode block in tracked markdown
// must render through vendored pseudocode.js + the runtime's \textcolor
// preprocessing. Pure Node — no browser needed. Missing `Semantics:` caption
// markers surface as warnings and do not fail this test.

const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const SCRIPT = path.join(__dirname, "..", "scripts", "check-pseudocode.cjs");

test("all tracked pseudocode blocks parse and render", () => {
  try {
    const out = execFileSync(process.execPath, [SCRIPT], {
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
    });
    assert.match(out, /0 error\(s\)/);
  } catch (error) {
    assert.fail(
      `pseudocode lint failed:\n${error.stdout || ""}\n${error.stderr || ""}`,
    );
  }
});

// The sweep above can legitimately find zero blocks (e.g. run from the
// canonical dir, whose repo has no lintable pseudocode fences) — a vacuous
// green. This fixture exercises explicit-file mode against a known-good
// block so the suite proves the pipeline ran regardless of cwd.
test("explicit-file lint actually scans blocks", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pclint-"));
  const file = path.join(dir, "fixture.md");
  fs.writeFileSync(
    file,
    [
      "# fixture",
      "",
      "```pseudocode",
      "\\begin{algorithm}",
      "\\caption{F\\\\{\\small\\textit{Semantics: 根据正文重构}}}",
      "\\begin{algorithmic}",
      "\\STATE $x \\gets 1$",
      "\\end{algorithmic}",
      "\\end{algorithm}",
      "```",
      "",
    ].join("\n"),
  );
  try {
    const out = execFileSync(process.execPath, [SCRIPT, file], {
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
    });
    assert.match(out, /1 block\(s\) in 1 file\(s\), 0 error\(s\)/);
  } catch (error) {
    assert.fail(
      `fixture lint failed:\n${error.stdout || ""}\n${error.stderr || ""}`,
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
