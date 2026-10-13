// Preview appearance picker — 跟随系统 + texlate 槽位色板 floating menu.
// Injected into every note's preview by parser.js via
//   @import "/.crossnote/theme-toggle.js"
// and gated by markdown-preview-enhanced.enablePreviewScripts + workspace
// trust. The script's only job is setting body[data-xnote-theme] to
// "system"/"editor" or a slot name — palette resolution lives in
// style.less ("editor" delegates to MPE's .markdown-preview.editor-dark
// tag; "system" follows prefers-color-scheme).
//
// State persists in localStorage for the webview's lifetime; a reopened
// preview starts back on "system" (each webview gets a fresh origin). In
// HTML export the /@import path is dead so the button never appears, and
// @media print hides it in PDF regardless.
(function () {
  "use strict";
  // Import sets can be re-fetched without a full reload — never double-mount.
  if (window.__xnoteThemeToggle) return;
  window.__xnoteThemeToggle = true;

  var STORAGE_KEY = "xnote-theme";
  var ORDER = ["system", "editor", "paper", "sepia", "snow", "dark", "onedark", "black"];
  var LABELS = {
    system: "跟随系统",
    editor: "跟随编辑器",
    paper: "暖纸",
    sepia: "羊皮纸",
    snow: "雪白",
    dark: "暖黑",
    onedark: "One Dark",
    black: "纯黑",
  };
  // Two-tone swatch per slot — 纸色/墨色 diagonal split, texlate style.
  var DOTS = {
    system: ["#f5f1e8", "#17140f"], // paper ↔ 暖黑 split: the two it flips between
    editor: ["#ffffff", "#1e1e1e"], // VS Code 亮/暗经典底色对半
    paper: ["#f5f1e8", "#211b12"],
    sepia: ["#f4ecd8", "#5b4636"],
    snow: ["#eceff4", "#3b4252"],
    dark: ["#17140f", "#e6ddcb"],
    onedark: ["#282c34", "#abb2bf"],
    black: ["#000000", "#ffffff"],
  };
  // Pre-slot localStorage values still select the same resolved palettes.
  var LEGACY = { light: "paper", dark: "dark" };

  function readState() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      if (LEGACY[v]) return LEGACY[v];
      return ORDER.indexOf(v) >= 0 ? v : "system";
    } catch (e) {
      return "system";
    }
  }

  function writeState(v) {
    try {
      localStorage.setItem(STORAGE_KEY, v);
    } catch (e) {
      // Storage disabled — the in-session override still applies.
    }
  }

  function dot(name) {
    var d = DOTS[name];
    return (
      '<span class="xnote-dot" style="background:linear-gradient(135deg,' +
      d[0] +
      " 50%," +
      d[1] +
      ' 50%)"></span>'
    );
  }

  var button = null;
  var menu = null;

  function render(state) {
    document.body.setAttribute("data-xnote-theme", state);
    if (button) {
      button.innerHTML = dot(state);
      var label = "外观：" + LABELS[state];
      button.title = label;
      button.setAttribute("aria-label", label);
    }
    if (menu) {
      var items = menu.querySelectorAll("[data-xnote-slot]");
      for (var i = 0; i < items.length; i++) {
        items[i].setAttribute(
          "aria-checked",
          items[i].getAttribute("data-xnote-slot") === state ? "true" : "false",
        );
      }
    }
  }

  function closeMenu() {
    if (!menu) return;
    menu.remove();
    menu = null;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", onDocClick, true);
    document.removeEventListener("keydown", onKeyDown, true);
  }

  function onDocClick(e) {
    if (menu && !menu.contains(e.target) && !button.contains(e.target))
      closeMenu();
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      closeMenu();
      button.focus();
    }
  }

  function select(name) {
    writeState(name);
    render(name);
    closeMenu();
  }

  function openMenu() {
    menu = document.createElement("div");
    menu.id = "xnote-theme-menu";
    // MPE counter-zooms `.fixed` chrome when the preview is zoomed — the
    // class is redundant styling-wise (id rule already sets position:fixed)
    // but keeps the menu pinned to the corner instead of drifting.
    menu.className = "fixed";
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "外观");
    var current = readState();
    for (var i = 0; i < ORDER.length; i++) {
      var name = ORDER[i];
      var item = document.createElement("button");
      item.type = "button";
      item.className = "xnote-theme-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("data-xnote-slot", name);
      item.setAttribute("aria-checked", name === current ? "true" : "false");
      item.innerHTML =
        dot(name) +
        '<span class="xnote-theme-label">' +
        LABELS[name] +
        "</span>" +
        '<span class="xnote-theme-check" aria-hidden="true">✓</span>';
      item.addEventListener("click", onItemClick);
      menu.appendChild(item);
    }
    document.body.appendChild(menu);
    button.setAttribute("aria-expanded", "true");
    // capture 阶段挂：menu 内 item 的 click 先命中 onItemClick 选槽关菜单，
    // 外部点击则由 onDocClick 关掉。
    document.addEventListener("click", onDocClick, true);
    document.addEventListener("keydown", onKeyDown, true);
  }

  function onItemClick(e) {
    e.stopPropagation();
    select(e.currentTarget.getAttribute("data-xnote-slot"));
  }

  function onButtonClick(e) {
    e.stopPropagation();
    if (menu) closeMenu();
    else openMenu();
  }

  function boot() {
    if (button || !document.body) return;
    button = document.createElement("button");
    button.id = "xnote-theme-toggle";
    button.className = "fixed";
    button.type = "button";
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", onButtonClick);
    document.body.appendChild(button);
    render(readState());
  }

  // The @import tag lands wherever crossnote places imports — body may not
  // exist yet when this runs.
  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
