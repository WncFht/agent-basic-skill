({
  katexConfig: {
  "macros": {}
},

  mathjaxConfig: {
  "tex": {},
  "options": {
    "enableEnrichment": false
  },
  "loader": {}
},

  mermaidConfig: {
  "startOnLoad": false
},

  // 注意：wikiLinkResolution 不能写在这里。crossnote 对该键按
  //「VS Code 设置 ?? config.js」取值，而扩展注册了默认值 "relative"，
  // get() 永远返回非空，config.js 的值永远被遮蔽。
  // 2026-09-23 起各仓统一不回写该键：保持默认 "relative" + 关闭
  // wikilink 语法，避免全工作区笔记索引拖慢首个预览（详见
  // references/crossnote.md 性能基线节）。
})
