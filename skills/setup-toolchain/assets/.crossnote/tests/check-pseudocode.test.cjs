"use strict";

// Unit tests for the lint's fence recognition and diagnostics — including
// blockquote-nested fences and info-string option warnings.

const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const check = require(path.join(
  __dirname,
  "..",
  "scripts",
  "check-pseudocode.cjs",
));

const VALID = String.raw`\begin{algorithm}
\caption{T\\{\small\textit{Semantics: 根据正文重构}}}
\begin{algorithmic}
\STATE x
\end{algorithmic}
\end{algorithm}`;

test("lints backtick, tilde, 4+-backtick, and indented fences", () => {
  for (const fence of [
    "```pseudocode",
    "~~~pseudocode",
    "````pseudocode",
    "   ```pseudocode",
  ]) {
    const marker = fence.match(/[`~]+/)[0];
    const text = `${fence}\n${VALID}\n${" ".repeat(fence.indexOf("`") > 0 ? 3 : 0)}${marker}\n`;
    const blocks = [...check.iterPseudocodeBlocks(text)];
    assert.equal(blocks.length, 1, fence);
  }
});

test("lints blockquote-nested fences and strips the quote prefix", () => {
  const text =
    "> quoted\n>\n" +
    "> ```pseudocode\n" +
    VALID.split("\n").map((l) => "> " + l).join("\n") +
    "\n> ```\n";
  const blocks = [...check.iterPseudocodeBlocks(text)];
  assert.equal(blocks.length, 1);
  // the quote markers must be stripped before rendering
  assert.equal(blocks[0].source, VALID);
  const problems = check.lintText("q.md", text).problems;
  assert.deepEqual(
    problems.map((p) => p.severity),
    [],
  );
});

test("a 4+-backtick outer fence swallows the inner block (not linted)", () => {
  const text = "````markdown\n```pseudocode\n" + VALID + "\n```\n````\n";
  assert.equal([...check.iterPseudocodeBlocks(text)].length, 0);
});

test("skips a backtick fence whose info contains a backtick", () => {
  const text = "```pseudocode `oops`\n" + VALID + "\n```\n";
  assert.equal([...check.iterPseudocodeBlocks(text)].length, 0);
});

test("error diagnostics point at the offending line, not the fence", () => {
  const text =
    "# T\n\n```pseudocode\n\\begin{algorithm}\n\\caption{T\\\\{\\small\\textit{Semantics: 根据正文重构}}}\n\\begin{algorithmic}\n\\STATE ok\n\\STATE \\BOGUSCMD\n\\end{algorithmic}\n\\end{algorithm}\n```\n";
  const problems = check.lintText("demo.md", text).problems;
  assert.equal(problems.length, 1);
  assert.equal(problems[0].severity, "error");
  assert.equal(problems[0].line, 8); // the \BOGUSCMD line, not the fence line 3
  assert.match(problems[0].message, /at position \d+/);
});

test("info-string problems surface as warnings", () => {
  const text = "```pseudocode nubmered indent=2px\n" + VALID + "\n```\n";
  const problems = check.lintText("w.md", text).problems;
  assert.deepEqual(
    problems.map((p) => p.severity),
    ["warning", "warning"],
  );
  assert.match(problems[0].message, /unknown flag 'nubmered'/);
  assert.match(problems[1].message, /indent=2px ignored/);
});

test("missing Semantics marker is a warning, never an error", () => {
  const text =
    "```pseudocode\n\\begin{algorithm}\n\\caption{T}\n\\begin{algorithmic}\n\\STATE x\n\\end{algorithmic}\n\\end{algorithm}\n```\n";
  const problems = check.lintText("w.md", text).problems;
  assert.deepEqual(problems.map((p) => p.severity), ["warning"]);
  assert.match(problems[0].message, /Semantics:/);
});

test("lints list-nested and ::: colon fences", () => {
  for (const text of [
    "- item\n  ```pseudocode\n" +
      VALID.split("\n")
        .map((l) => "  " + l)
        .join("\n") +
      "\n  ```\n",
    ":::pseudocode\n" + VALID + "\n:::\n",
    "1. item\n   ```pseudocode\n" +
      VALID.split("\n")
        .map((l) => "   " + l)
        .join("\n") +
      "\n   ```\n",
  ]) {
    const blocks = [...check.iterPseudocodeBlocks(text)];
    assert.equal(blocks.length, 1, JSON.stringify(text.slice(0, 40)));
    assert.equal(blocks[0].source, VALID);
  }
});

test("lints an unclosed fence to end of document", () => {
  // CommonMark renders an unclosed opener to EOF — a mid-edit save that
  // deleted the closer still gets linted, not silently skipped.
  const text = "```pseudocode\n" + VALID + "\n";
  const blocks = [...check.iterPseudocodeBlocks(text)];
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].source, VALID + "\n");
});

test("nested blockquote strips one level per depth — inner > survives", () => {
  // `> >foo` inside a depth-1 quote block renders as literal `>foo`; the
  // stripper must consume exactly one group, not every `>` on the line.
  const text =
    "> ```pseudocode\n" +
    "> \\begin{algorithm}\n" +
    "> \\caption{T\\\\{\\small\\textit{Semantics: 根据正文重构}}}\n" +
    "> \\begin{algorithmic}\n" +
    "> > stray\n" +
    "> \\end{algorithmic}\n" +
    "> \\end{algorithm}\n" +
    "> ```\n";
  const blocks = [...check.iterPseudocodeBlocks(text)];
  assert.equal(blocks.length, 1);
  // the doubly-quoted line keeps its inner `>` — the renderer sees `> stray`
  assert.match(blocks[0].source, /> stray/);
});

test("--staged lints staged content in the invoking repo", () => {
  const fs = require("node:fs");
  const os = require("node:os");
  const { execFileSync, spawnSync } = require("node:child_process");
  const script = path.join(__dirname, "..", "scripts", "check-pseudocode.cjs");
  const repo = fs.mkdtempSync(path.join(os.tmpdir(), "lint-staged-"));
  const git = (args) => execFileSync("git", args, { cwd: repo });

  git(["init", "-q"]);
  fs.writeFileSync(
    path.join(repo, "bad.md"),
    "```pseudocode\n\\BOGUS\n```\n",
  );
  fs.writeFileSync(
    path.join(repo, "good.md"),
    "```pseudocode\n" + VALID + "\n```\n",
  );

  // Unstaged only — nothing in the index, so --staged finds nothing.
  const clean = spawnSync(process.execPath, [script, "--staged"], {
    cwd: repo,
    encoding: "utf8",
  });
  assert.equal(clean.status, 0, clean.stderr + clean.stdout);
  assert.match(clean.stdout, /0 block\(s\)/);

  git(["add", "bad.md"]);
  const dirty = spawnSync(process.execPath, [script, "--staged"], {
    cwd: repo,
    encoding: "utf8",
  });
  assert.equal(dirty.status, 1, dirty.stderr + dirty.stdout);
  assert.match(dirty.stdout, /bad\.md:\d+: error:/);
  assert.doesNotMatch(dirty.stdout, /good\.md/);

  // --staged takes no file arguments.
  const misuse = spawnSync(process.execPath, [script, "--staged", "bad.md"], {
    cwd: repo,
    encoding: "utf8",
  });
  assert.equal(misuse.status, 2);
});

test("unknown flags exit 2 instead of ENOENT-ing as filenames", () => {
  const { spawnSync } = require("node:child_process");
  const script = path.join(__dirname, "..", "scripts", "check-pseudocode.cjs");
  const res = spawnSync(process.execPath, [script, "--bogus"], {
    encoding: "utf8",
  });
  assert.equal(res.status, 2);
  assert.match(res.stderr, /unknown flag --bogus/);
});
