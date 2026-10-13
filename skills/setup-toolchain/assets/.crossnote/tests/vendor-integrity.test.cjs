"use strict";

// Vendor integrity: vendored builds must match the SHA-256 sums recorded in
// vendor/README.md, so a corrupted or accidentally modified dependency fails
// loudly instead of breaking preview rendering in surprising ways.

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const VENDOR = path.resolve(__dirname, "..", "vendor");

const EXPECTED_SHA256 = {
  "katex-0.16.47.min.js":
    "a29d2961d3146de5949d78ac7c1a9d93ae54955bad22a6db4fbe836e88e8bf48",
  "pseudocode-2.4.1.min.js":
    "695903c6acb3ac1f84c54b0e63d3ddc9e9640e19ff0dfae35aed3c695a6a365a",
};

for (const [file, sha256] of Object.entries(EXPECTED_SHA256)) {
  test(`vendor checksum: ${file}`, () => {
    const digest = crypto
      .createHash("sha256")
      .update(fs.readFileSync(path.join(VENDOR, file)))
      .digest("hex");
    assert.equal(digest, sha256);
  });
}
