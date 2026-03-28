---
name: tauri-devtools-ui-automation
description: Tauri 应用 UI 自动化操作指南。提供截图、DOM Snapshot、元素查找、样式获取、点击交互、键盘输入、等待元素和执行 JavaScript 等功能。
---

# UI 自动化

用于检查、操作 WebView 内容的核心功能集合。

---

## 📸 截图

捕获 WebView 当前画面。

```bash
# 基础截图
tauri-mcp webview-screenshot --file screenshot.png

# 指定格式和质量（JPEG）
tauri-mcp webview-screenshot --file screenshot.jpg --format jpeg --quality 90

# 限制最大宽度（自动缩放）
tauri-mcp webview-screenshot --file screenshot.png --max-width 1200
```

**常用场景：**
- 记录 UI 状态
- 对比操作前后变化
- 生成测试报告

---

## 🌲 DOM Snapshot

获取结构化 DOM 树，支持两种格式。

### Accessibility 树

适合理解 UI 语义、查找交互元素。

```bash
tauri-mcp webview-dom-snapshot --type accessibility
```

**输出示例：**
```yaml
- banner [ref=e3]:
  - button 添加 Gateway 实例 [ref=e20] [cursor=pointer]
  - button 登录 [ref=e31] [cursor=pointer]
- main [ref=e36]:
  - button 聊天 [ref=e41] [cursor=pointer]
```

### Structure 树

适合调试 CSS、查找元素选择器。

```bash
tauri-mcp webview-dom-snapshot --type structure
```

**输出示例：**
```yaml
- body [ref=e0]:
  - div#root [ref=e1]:
    - header.sticky.top-0 [ref=e3]:
      - button.MuiButtonBase-root [ref=e26]
```

**关键特性：** 每个元素都有 `[ref=eN]` ID，可用于后续操作。

---

## 🔍 查找元素

通过选择器定位元素。

```bash
# CSS 选择器（默认）
tauri-mcp webview-find-element --selector "button"
tauri-mcp webview-find-element --selector "#app"
tauri-mcp webview-find-element --selector ".navbar"

# XPath
tauri-mcp webview-find-element --selector "//button[text()='Submit']" --strategy xpath

# ref ID（从 DOM Snapshot 获取）
tauri-mcp webview-find-element --selector "ref=e20"
```

**输出：** 返回元素的 HTML 字符串，以及匹配数量。

---

## 🎨 获取计算样式

获取元素的 CSS 样式。

```bash
# 获取所有样式
tauri-mcp webview-get-styles --selector "body"

# 获取特定属性
tauri-mcp webview-get-styles --selector "button" --properties '["color", "background-color"]'

# 使用 ref ID
tauri-mcp webview-get-styles --selector "ref=e20"
```

---

## 👆 元素交互

### 点击

```bash
# 点击元素（CSS 选择器）
tauri-mcp webview-interact --action click --selector "button"

# 点击坐标
tauri-mcp webview-interact --action click --x 100 --y 200

# 双击
tauri-mcp webview-interact --action double-click --selector "#item"

# 长按
tauri-mcp webview-interact --action long-press --selector "#target" --duration 1000
```

### 聚焦

```bash
tauri-mcp webview-interact --action focus --selector "input"
```

### 滚动

```bash
# 垂直滚动
tauri-mcp webview-interact --action scroll --scrollY 300

# 水平滚动
tauri-mcp webview-interact --action scroll --scrollX 100
```

### 滑动手势

```bash
tauri-mcp webview-interact --action swipe --fromX 100 --fromY 100 --toX 300 --toY 300 --duration 500
```

---

## ⌨️ 键盘操作

```bash
# 按键
tauri-mcp webview-keyboard --action press --key "Enter"
tauri-mcp webview-keyboard --action press --key "Escape"
tauri-mcp webview-keyboard --action press --key "a" --modifiers '["Control"]'

# 组合键
tauri-mcp webview-keyboard --action press --key "c" --modifiers '["Control"]'

# 在输入框中输入文本
tauri-mcp webview-keyboard --action type --selector "#username" --text "hello world"
```

---

## ⏱️ 等待元素

等待元素出现或特定文本。

```bash
# 等待选择器
tauri-mcp webview-wait-for --type selector --value "button"

# 等待文本出现
tauri-mcp webview-wait-for --type text --value "Loading complete"

# 自定义超时时间（默认 5000ms）
tauri-mcp webview-wait-for --type selector --value "#result" --timeout 10000
```

---

## 📜 执行 JavaScript

在 WebView 上下文中执行任意 JS。

```bash
# 简单表达式
tauri-mcp webview-execute-js --script "document.title"

# 带返回值（使用 IIFE）
tauri-mcp webview-execute-js --script '
  (() => {
    return {
      url: window.location.href,
      title: document.title,
      buttons: document.querySelectorAll("button").length
    };
  })()
'

# 传参
tauri-mcp webview-execute-js --script '
  (function(a, b) { return a + b; })
' --raw '{"args": [5, 3]}'
```

**注意：** 返回值必须是 JSON 可序列化的。

---

## 实用技巧

### 技巧 1：使用 ref ID 精确操作

```bash
# 1. 先获取 DOM 看 ref IDs
tauri-mcp webview-dom-snapshot --type accessibility

# 2. 使用 ref ID 点击特定按钮
tauri-mcp webview-interact --action click --selector "ref=e20"
```

### 技巧 2：配合截图验证

```bash
# 操作前截图
tauri-mcp webview-screenshot --file before.png

# 执行操作
tauri-mcp webview-interact --action click --selector "#submit"

# 操作后截图对比
tauri-mcp webview-screenshot --file after.png
```

### 技巧 3：批量获取元素信息

```bash
# 获取所有按钮的文本
tauri-mcp webview-execute-js --script '
  Array.from(document.querySelectorAll("button")).map(b => b.textContent)
'
```

---

## 故障排除

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `resolveRef is not a function` | 前端辅助函数未注入 | [查看初始化配置](../setup/SETUP.md) |
| `Element not found` | 选择器错误或元素未加载 | 检查选择器，或先用 `wait-for` |
| `Script execution timeout` | `withGlobalTauri` 未启用 | [查看初始化配置](../setup/SETUP.md) |
