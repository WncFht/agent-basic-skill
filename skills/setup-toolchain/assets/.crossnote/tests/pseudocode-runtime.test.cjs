"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { after, before, test } = require("node:test");

const crossnoteRoot = path.resolve(__dirname, "..");
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const algorithm = String.raw`\begin{algorithm}
\caption{Test algorithm}
\begin{algorithmic}
\STATE hello
\end{algorithmic}
\end{algorithm}`;

let browser;
let baseUrl;
let server;

// Browser e2e needs playwright — an optional dep that lives outside this repo.
// Resolve it up front so a missing install marks every test as skipped
// instead of failing inside before().
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

function contentType(filename) {
  if (filename.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filename.endsWith(".html")) return "text/html; charset=utf-8";
  return "application/octet-stream";
}

function fixture(runtimePath = "/pseudocode-runtime.js") {
  return `<!doctype html>
<html><head><meta charset="utf-8"></head>
<body><main class="markdown-preview" id="preview"></main>
<script src="${runtimePath}"></script></body></html>`;
}

function serve(request, response) {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname === "/fixture.html") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(fixture(url.searchParams.get("runtime") || undefined));
    return;
  }

  let relativePath = url.pathname.replace(/^\/(?:broken\/)?/, "");
  if (url.pathname.startsWith("/broken/vendor/")) {
    response.writeHead(404);
    response.end("missing dependency");
    return;
  }
  if (url.pathname === "/broken/pseudocode-runtime.js") {
    relativePath = "pseudocode-runtime.js";
  }

  const filename = path.join(crossnoteRoot, relativePath);
  if (!filename.startsWith(crossnoteRoot + path.sep) || !fs.existsSync(filename)) {
    response.writeHead(404);
    response.end("not found");
    return;
  }
  response.writeHead(200, { "content-type": contentType(filename) });
  fs.createReadStream(filename).pipe(response);
}

async function openFixture(runtimePath) {
  const page = await browser.newPage();
  const query = runtimePath ? `?runtime=${encodeURIComponent(runtimePath)}` : "";
  await page.goto(`${baseUrl}/fixture.html${query}`);
  return page;
}

async function appendSource(page, shape, source = algorithm) {
  await page.evaluate(({ shape, source }) => {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    if (shape === "current") pre.className = "language-pseudocode pseudocode";
    else code.className = "language-pseudocode";
    code.textContent = source;
    pre.appendChild(code);
    document.querySelector("#preview").appendChild(pre);
  }, { shape, source });
}

async function waitForRendered(page, count) {
  await page.waitForFunction(
    (expected) => document.querySelectorAll(".crossnote-pseudocode").length === expected,
    count,
  );
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

it("loads no vendor scripts when the document has no pseudocode", async () => {
  const page = await openFixture();
  await page.waitForTimeout(100);
  assert.equal(
    await page.locator("script[data-crossnote-pseudocode-dependency]").count(),
    0,
  );
  await page.close();
});

it("renders current and legacy MPE DOM without duplicate output", async () => {
  const page = await openFixture();
  await appendSource(page, "current");
  await appendSource(page, "legacy");
  await waitForRendered(page, 2);

  const result = await page.evaluate(() => ({
    captions: Array.from(document.querySelectorAll(".crossnote-pseudocode"))
      .map((node) => node.textContent.match(/Algorithm\s+\d+/)?.[0]),
    errors: document.querySelectorAll(".pseudocode-error").length,
    figures: Array.from(document.querySelectorAll("figure.crossnote-pseudocode"))
      .every((node) => {
        const id = node.getAttribute("aria-labelledby");
        return node.getAttribute("role") === "figure" && id && document.getElementById(id);
      }),
  }));
  assert.deepEqual(result.captions, ["Algorithm 1", "Algorithm 2"]);
  assert.equal(result.errors, 0);
  assert.equal(result.figures, true);

  await page.evaluate(() => {
    window.__crossnotePseudocodeRuntime.queueRender();
    window.__crossnotePseudocodeRuntime.queueRender();
  });
  await page.waitForTimeout(100);
  assert.equal(await page.locator(".crossnote-pseudocode").count(), 2);
  await page.close();
});

it("applies per-block options from the pre's data-info attribute", async () => {
  const page = await openFixture();
  await page.evaluate((source) => {
    const pre = document.createElement("pre");
    pre.className = "language-pseudocode";
    // crossnote's fence renderer writes the raw info string to data-info.
    pre.dataset.info = "pseudocode numbered title=Spec";
    const code = document.createElement("code");
    code.textContent = source;
    pre.appendChild(code);
    document.querySelector("#preview").appendChild(pre);
  }, algorithm);
  await waitForRendered(page, 1);

  const result = await page.evaluate(() => ({
    linenums: document.querySelectorAll(".crossnote-pseudocode .ps-linenum")
      .length,
    caption: document.querySelector(".crossnote-pseudocode").textContent,
    errors: document.querySelectorAll(".pseudocode-error").length,
  }));
  assert.ok(result.linenums > 0, "numbered flag should render line numbers");
  assert.match(result.caption, /Spec 1\s+Test algorithm/);
  assert.equal(result.errors, 0);
  await page.close();
});

it("preserves an existing KaTeX global", async () => {
  const page = await openFixture();
  await page.addScriptTag({ url: `${baseUrl}/vendor/katex-0.16.47.min.js` });
  await page.evaluate(() => { window.__originalKatex = window.katex; });
  await appendSource(page, "current");
  await waitForRendered(page, 1);

  const result = await page.evaluate(() => ({
    sameKatex: window.katex === window.__originalKatex,
    runtimeKatexLoads: document.querySelectorAll(
      "script[data-crossnote-pseudocode-dependency='katex']",
    ).length,
  }));
  assert.equal(result.sameKatex, true);
  assert.equal(result.runtimeKatexLoads, 0);
  await page.close();
});

it("handles nested manual colors and leaves math colors to KaTeX", async () => {
  const page = await openFixture();
  const colored = String.raw`\begin{algorithm}
\caption{Colored algorithm}
\begin{algorithmic}
\STATE \textcolor{red}{outer \textcolor{blue}{inner}}
\STATE $\textcolor{green}{inline}$
\end{algorithmic}
\end{algorithm}`;
  await appendSource(page, "current", colored);
  await waitForRendered(page, 1);

  assert.deepEqual(
    await page.evaluate(() => ({
      blue: document.querySelectorAll(".ps-manual-color.ps-color-blue").length,
      errors: document.querySelectorAll(".pseudocode-error").length,
      green: document.querySelectorAll(".ps-manual-color.ps-color-green").length,
      red: document.querySelectorAll(".ps-manual-color.ps-color-red").length,
    })),
    { blue: 1, errors: 0, green: 0, red: 1 },
  );

  const scanned = await page.evaluate(() => (
    window.__crossnotePseudocodeRuntime.inspectTextColors(String.raw`
      \textcolor{red}{outside}
      $\textcolor{green}{inline}$
      $$\textcolor{purple}{display}$$
      \(\textcolor{blue}{paren}\)
      \[\textcolor{orange}{bracketed}\]
    `)
  ));
  assert.equal(scanned.markers.length, 1);
  assert.match(scanned.source, /\\textcolor\{green\}\{inline\}/);
  assert.match(scanned.source, /\\textcolor\{purple\}\{display\}/);
  assert.match(scanned.source, /\\textcolor\{blue\}\{paren\}/);
  assert.match(scanned.source, /\\textcolor\{orange\}\{bracketed\}/);
  await page.close();
});

it("shows source errors without replacing the original block", async () => {
  const page = await openFixture();
  const invalid = algorithm.replace("\\STATE hello", "\\STATE \\textcolor{cyan}{hello}");
  await appendSource(page, "current", invalid);
  await page.waitForSelector(".pseudocode-error");

  assert.deepEqual(
    await page.evaluate(() => ({
      alert: document.querySelector(".pseudocode-error").getAttribute("role"),
      rendered: document.querySelectorAll(".crossnote-pseudocode").length,
      source: document.querySelectorAll("pre.language-pseudocode").length,
      text: document.querySelector(".pseudocode-error").textContent,
    })),
    {
      alert: "alert",
      rendered: 0,
      source: 1,
      text: "Pseudocode render error: Unsupported text color 'cyan'. Use red, blue, green, orange, purple, or gray.",
    },
  );
  await page.close();
});

it("shows a retryable diagnostic when dependencies fail", async () => {
  const page = await openFixture("/broken/pseudocode-runtime.js");
  await appendSource(page, "current");
  await page.waitForSelector(".pseudocode-error .pseudocode-retry");

  assert.match(
    await page.locator(".pseudocode-error").textContent(),
    /Pseudocode render error: Failed to load .*katex-0\.16\.47\.min\.js\.Retry/,
  );
  await page.close();
});

it("renders a pseudocode block added by a preview rebuild", async () => {
  const page = await openFixture();
  await appendSource(page, "current");
  await waitForRendered(page, 1);

  await page.evaluate((source) => {
    const preview = document.createElement("main");
    preview.className = "markdown-preview";
    preview.id = "preview";
    const pre = document.createElement("pre");
    pre.className = "language-pseudocode";
    const code = document.createElement("code");
    code.textContent = source.replace("Test algorithm", "Rebuilt algorithm");
    pre.appendChild(code);
    preview.appendChild(pre);
    document.querySelector("#preview").replaceWith(preview);
  }, algorithm);
  await waitForRendered(page, 1);

  assert.match(
    await page.locator(".crossnote-pseudocode").textContent(),
    /Algorithm 1\s+Rebuilt algorithm/,
  );
  await page.close();
});

it("re-stamps caption numbers when a block is inserted mid-document", async () => {
  const page = await openFixture();
  await appendSource(page, "current", algorithm.replace("Test algorithm", "One"));
  await appendSource(page, "current", algorithm.replace("Test algorithm", "Two"));
  await waitForRendered(page, 2);

  // Insert a new source ahead of both rendered figures — every figure below
  // must renumber (and keep aria-labelledby + caption id unique).
  await page.evaluate((source) => {
    const pre = document.createElement("pre");
    pre.className = "language-pseudocode";
    const code = document.createElement("code");
    code.textContent = source;
    pre.appendChild(code);
    document.querySelector("#preview").prepend(pre);
  }, algorithm.replace("Test algorithm", "Zero"));
  await waitForRendered(page, 3);

  const result = await page.evaluate(() => ({
    captions: Array.from(document.querySelectorAll(".crossnote-pseudocode"))
      .map((node) => node.textContent.match(/Algorithm\s+\d+/)?.[0]),
    ids: Array.from(
      document.querySelectorAll("[id^='crossnote-pseudocode-caption-']"),
    ).map((node) => node.id),
    labelRefs: Array.from(document.querySelectorAll(".crossnote-pseudocode"))
      .map((node) => node.getAttribute("aria-labelledby")),
  }));
  assert.deepEqual(result.captions, ["Algorithm 1", "Algorithm 2", "Algorithm 3"]);
  assert.equal(new Set(result.ids).size, result.ids.length);
  for (const ref of result.labelRefs) {
    assert.ok(result.ids.includes(ref), `aria-labelledby ${ref} resolves`);
  }
  await page.close();
});

it("multi-\\caption blocks consume their real number span", async () => {
  const two = String.raw`\begin{algorithm}
\caption{First}
\caption{Second}
\begin{algorithmic}
\STATE x
\end{algorithmic}
\end{algorithm}`;
  const page = await openFixture();
  await appendSource(page, "current", two);
  await appendSource(page, "current");
  await waitForRendered(page, 2);

  const result = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".crossnote-pseudocode")).map(
      (node) => ({
        caption: node.textContent.match(/Algorithm\s+\d+/)?.[0],
        index: node.getAttribute("data-caption-index"),
        count: node.getAttribute("data-caption-count"),
      }),
    ),
  );
  // Vendored renderer keeps the last caption only, but still consumes both
  // numbers — the second block must continue at 3.
  assert.deepEqual(result, [
    { caption: "Algorithm 2", index: "1", count: "2" },
    { caption: "Algorithm 3", index: "3", count: "1" },
  ]);
  await page.close();
});

it("skips sources staged inside .hidden-preview until they go live", async () => {
  const page = await openFixture();
  await page.evaluate((source) => {
    const staging = document.createElement("div");
    staging.className = "hidden-preview";
    const pre = document.createElement("pre");
    pre.className = "language-pseudocode";
    const code = document.createElement("code");
    code.textContent = source;
    pre.appendChild(code);
    staging.appendChild(pre);
    document.querySelector("#preview").appendChild(staging);
  }, algorithm);
  await page.waitForTimeout(200);
  // The staging buffer must not render nor consume caption numbers.
  assert.equal(await page.locator(".crossnote-pseudocode").count(), 0);

  await appendSource(page, "current");
  await waitForRendered(page, 1);
  assert.match(
    await page.locator(".crossnote-pseudocode").textContent(),
    /Algorithm 1/,
  );
  await page.close();
});

it("clicking retry reloads the dependency scripts", async () => {
  const page = await openFixture("/broken/pseudocode-runtime.js");
  let katexRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("katex-0.16.47.min.js")) katexRequests += 1;
  });
  await appendSource(page, "current");
  await page.waitForSelector(".pseudocode-error .pseudocode-retry");
  assert.equal(katexRequests, 1);

  await page.locator(".pseudocode-retry").click();
  await page.waitForSelector(".pseudocode-error .pseudocode-retry");
  // Deps still 404, so the error returns — but only after a real reload
  // attempt pushed a second request for the vendored script.
  assert.equal(katexRequests, 2);
  await page.close();
});

it("defers to an existing observerActive runtime instead of double-observing", async () => {
  const page = await openFixture();
  // Simulate a version-skewed re-execution: an older export whose observer
  // already owns the document must not be replaced or doubled.
  await page.evaluate(() => {
    window.__skewRenderCalls = 0;
    window.__crossnotePseudocodeRuntime = {
      observerActive: true,
      queueRender() {
        window.__skewRenderCalls += 1;
      },
    };
  });
  await page.addScriptTag({ url: `${baseUrl}/pseudocode-runtime.js` });
  await page.waitForFunction(() => window.__skewRenderCalls > 0);
  assert.equal(
    await page.evaluate(() => window.__crossnotePseudocodeRuntime.version),
    undefined,
  );
  await page.close();
});
