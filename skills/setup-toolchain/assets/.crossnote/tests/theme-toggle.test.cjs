"use strict";

// Browser e2e for theme-toggle.js — the palette chrome is DOM-only, so it
// can't be covered by the vm tests. Skipped where playwright is unavailable
// (same optional-dep gate as pseudocode-runtime.test.cjs).

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { after, before, test } = require("node:test");

const crossnoteRoot = path.resolve(__dirname, "..");
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const SLOTS = ["system", "editor", "paper", "sepia", "snow", "dark", "onedark", "black"];

let browser;
let baseUrl;
let server;

let playwright = null;
let playwrightError = null;
try {
  playwright = loadPlaywright();
} catch (error) {
  playwrightError = error;
}
if (!playwright) {
  process.emitWarning(
    `playwright unavailable (${playwrightError.code || playwrightError.message}); skipping browser e2e tests`,
  );
}
const it = playwright ? test : test.skip;

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (originalError) {
    const runtimesRoot = path.join(os.homedir(), ".cache", "codex-runtimes");
    if (fs.existsSync(runtimesRoot)) {
      const versions = fs.readdirSync(runtimesRoot).sort().reverse();
      for (const version of versions) {
        const candidate = path.join(
          runtimesRoot,
          version,
          "dependencies",
          "node",
          "node_modules",
          "playwright",
        );
        if (fs.existsSync(candidate)) return require(candidate);
      }
    }
    throw originalError;
  }
}

function serve(request, response) {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname === "/fixture.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(`<!doctype html>
<html><head><meta charset="utf-8"></head>
<body><main class="markdown-preview" id="preview"><p>note</p></main>
<script src="/theme-toggle.js"></script></body></html>`);
    return;
  }
  const filename = path.join(crossnoteRoot, url.pathname.slice(1));
  if (!filename.startsWith(crossnoteRoot + path.sep) || !fs.existsSync(filename)) {
    response.writeHead(404);
    response.end("not found");
    return;
  }
  response.writeHead(200, {
    "content-type": filename.endsWith(".js")
      ? "text/javascript; charset=utf-8"
      : "application/octet-stream",
  });
  fs.createReadStream(filename).pipe(response);
}

async function openFixture() {
  const page = await browser.newPage();
  await page.goto(`${baseUrl}/fixture.html`);
  await page.waitForSelector("#xnote-theme-toggle");
  return page;
}

before(async () => {
  if (!playwright) return;
  const { chromium } = playwright;
  browser = await chromium.launch({
    executablePath: fs.existsSync(chromePath) ? chromePath : undefined,
    headless: true,
  });
  server = http.createServer(serve);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

it("mounts one pinned button defaulting to system", async () => {
  const page = await openFixture();
  const button = page.locator("#xnote-theme-toggle");
  assert.equal(await button.count(), 1);
  // class="fixed" is what MPE's zoom counter-scale matches — losing it
  // drifts the chrome on every zoom level.
  assert.match(await button.getAttribute("class"), /\bfixed\b/);
  assert.equal(await button.getAttribute("aria-haspopup"), "menu");
  assert.equal(await button.getAttribute("aria-expanded"), "false");
  assert.equal(
    await page.evaluate(() => document.body.getAttribute("data-xnote-theme")),
    "system",
  );
  await page.close();
});

it("lists all 8 slots and applies the selected palette", async () => {
  const page = await openFixture();
  await page.locator("#xnote-theme-toggle").click();
  const menu = page.locator("#xnote-theme-menu");
  assert.match(await menu.getAttribute("class"), /\bfixed\b/);
  assert.equal(await menu.getAttribute("role"), "menu");
  assert.equal(
    await page.locator("#xnote-theme-toggle").getAttribute("aria-expanded"),
    "true",
  );

  const slots = await page
    .locator("#xnote-theme-menu [data-xnote-slot]")
    .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-xnote-slot")));
  assert.deepEqual(slots, SLOTS);
  assert.equal(
    await page
      .locator('#xnote-theme-menu [data-xnote-slot="system"]')
      .getAttribute("aria-checked"),
    "true",
  );

  await page.locator('#xnote-theme-menu [data-xnote-slot="sepia"]').click();
  assert.equal(
    await page.evaluate(() => document.body.getAttribute("data-xnote-theme")),
    "sepia",
  );
  assert.equal(
    await page.evaluate(() => localStorage.getItem("xnote-theme")),
    "sepia",
  );
  assert.equal(await page.locator("#xnote-theme-menu").count(), 0);
  assert.equal(
    await page.locator("#xnote-theme-toggle").getAttribute("aria-expanded"),
    "false",
  );
  await page.close();
});

it("resolves legacy localStorage values to their slot equivalents", async () => {
  const page = await browser.newPage();
  await page.addInitScript(() => localStorage.setItem("xnote-theme", "light"));
  await page.goto(`${baseUrl}/fixture.html`);
  await page.waitForSelector("#xnote-theme-toggle");
  assert.equal(
    await page.evaluate(() => document.body.getAttribute("data-xnote-theme")),
    "paper",
  );
  await page.close();
});

it("falls back to system for missing or unknown stored values", async () => {
  const page = await browser.newPage();
  await page.addInitScript(() => localStorage.setItem("xnote-theme", "bogus"));
  await page.goto(`${baseUrl}/fixture.html`);
  await page.waitForSelector("#xnote-theme-toggle");
  assert.equal(
    await page.evaluate(() => document.body.getAttribute("data-xnote-theme")),
    "system",
  );
  await page.close();
});

it("closes the menu on Escape and on outside click", async () => {
  const page = await openFixture();
  const toggle = page.locator("#xnote-theme-toggle");
  await toggle.click();
  assert.equal(await page.locator("#xnote-theme-menu").count(), 1);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#xnote-theme-menu").count(), 0);
  assert.equal(await toggle.getAttribute("aria-expanded"), "false");

  await toggle.click();
  await page.locator("#preview").click();
  assert.equal(await page.locator("#xnote-theme-menu").count(), 0);
  await page.close();
});

it("does not double-mount when the import is re-fetched", async () => {
  const page = await openFixture();
  await page.addScriptTag({ url: `${baseUrl}/theme-toggle.js` });
  await page.waitForTimeout(100);
  assert.equal(await page.locator("#xnote-theme-toggle").count(), 1);
  await page.close();
});
