# Pseudocode runtime dependencies

- `katex-0.16.47.min.js`: KaTeX 0.16.47 browser build, MIT license.
- `pseudocode-2.4.1.min.js`: pseudocode.js 2.4.1 browser build, MIT license.

SHA-256 checksums (enforced by `tests/vendor-integrity.test.cjs`):

- `katex-0.16.47.min.js`: `a29d2961d3146de5949d78ac7c1a9d93ae54955bad22a6db4fbe836e88e8bf48`
- `pseudocode-2.4.1.min.js`: `695903c6acb3ac1f84c54b0e63d3ddc9e9640e19ff0dfae35aed3c695a6a365a`

The corresponding license files are stored beside the builds. Versions are pinned so Crossnote previews do not depend on a CDN or change unexpectedly.

## Version pinning policy

- `pseudocode-*.min.js` tracks upstream releases
  (<https://github.com/SaswatPadhi/pseudocode.js>).
- `katex-*.min.js` must match the KaTeX version bundled with the installed Markdown Preview Enhanced extension — the rendered markup and the preview's `katex.min.css` come from the same build. Do **not** track upstream KaTeX: v0.18 renamed CSS classes (breaking change) and would render unstyled against MPE's older stylesheet. MPE 0.8.35 bundles KaTeX 0.16.47 (visible in `crossnote/dependencies/katex/` inside the extension). When the extension bumps its KaTeX, bump the vendored file to match and update the checksum above and in the test.
