---
name: web-devtools-ui-automation
description: Web UI 自动化操作指南。提供浏览器自动化核心功能，包括截图、元素检查、点击、输入、表单填写、JavaScript 执行和 Python 自动化。
---

# UI 自动化

核心调试功能：截图、元素检查、点击、输入、表单填写等。

---

## 📸 截图

捕获网页当前画面。

```bash
# 基础截图
browser-use screenshot output.png

# 不保存文件，输出 base64
browser-use screenshot

# 完整页面截图
browser-use screenshot --full fullpage.png
```

**输出示例（无路径）：**
```
iVBORw0KGgoAAAANSUhEUgAABQAAAALQCAYAAADPfd1W...
```

---

## 🔍 获取页面状态

获取 URL、标题和可点击元素列表（带索引）。

```bash
browser-use state
```

**输出示例：**
```
URL: https://example.com
Title: Example Domain

[0] button "Sign In"
[1] input "Email"
[2] input "Password"
[3] link "Forgot password?"
[4] button "Submit"
```

**关键概念：**
- 每个交互元素都有数字索引（如 `[0]`, `[1]`）
- 使用索引进行点击、输入等操作
- 索引每次 `state` 调用都可能变化（页面更新后）

---

## 👆 点击元素

### 按索引点击

```bash
# 点击元素索引 5
browser-use click 5
```

### 按坐标点击

```bash
# 点击坐标 (100, 200)
browser-use click 100 200
```

### 双击

```bash
browser-use dblclick 5
```

### 右键点击

```bash
browser-use rightclick 5
```

### 悬停

```bash
browser-use hover 5
```

---

## ⌨️ 输入文本

### 在聚焦元素输入

```bash
# 先点击输入框，然后输入
browser-use click 1
browser-use type "Hello World"
```

### 一键输入（点击+输入）

```bash
# 点击元素索引 1，然后输入文本
browser-use input 1 "john@example.com"
```

### 按键

```bash
# 按单个键
browser-use keys "Enter"

# 按组合键
browser-use keys "Control+a"
browser-use keys "Control+c"
browser-use keys "Command+v"  # macOS
```

**常用按键：**
- `Enter`, `Escape`, `Tab`, `Backspace`
- `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`
- `Control`, `Alt`, `Shift`, `Command` (macOS)

---

## 📋 表单操作

### 填写完整表单

```bash
# 打开页面
browser-use open https://example.com/form

# 查看元素
browser-use state
# [0] input "Name"
# [1] input "Email"
# [2] select "Country"
# [3] button "Submit"

# 填写表单
browser-use input 0 "John Doe"
browser-use input 1 "john@example.com"
browser-use select 2 "United States"

# 提交
browser-use click 3
```

### 下拉选择

```bash
# 选择下拉选项
browser-use select 2 "Option Value"
```

### 文件上传

```bash
# 上传文件到 file input 元素
browser-use upload 5 /path/to/file.pdf
```

---

## 📋 获取元素信息

### 获取文本内容

```bash
browser-use get text 5
```

### 获取输入值

```bash
browser-use get value 1
```

### 获取元素属性

```bash
browser-use get attributes 5
```

**输出示例：**
```json
{
  "id": "submit-btn",
  "class": "btn btn-primary",
  "data-value": "123"
}
```

### 获取元素位置

```bash
browser-use get bbox 5
```

**输出示例：**
```json
{
  "x": 100,
  "y": 200,
  "width": 120,
  "height": 40
}
```

---

## 📜 JavaScript 执行

在页面上下文中执行 JavaScript。

```bash
# 简单表达式
browser-use eval "document.title"

# 获取元素
browser-use eval "document.querySelector('h1').textContent"

# 复杂操作
browser-use eval "
Array.from(document.querySelectorAll('.item'))
  .map(el => el.textContent)
  .slice(0, 5)
"
```

---

## ⏱️ 等待元素

### 等待元素可见

```bash
# 等待 CSS 选择器元素出现
browser-use wait selector ".loading"

# 等待元素消失
browser-use wait selector ".loading" --state hidden

# 自定义超时（毫秒）
browser-use wait selector "h1" --timeout 5000
```

### 等待文本出现

```bash
browser-use wait text "Success"
```

---

## 🐍 Python 自动化

使用持久化 Python 会话进行复杂自动化。

### 设置变量

```bash
browser-use python "x = 42"
```

### 访问变量

```bash
browser-use python "print(x)"
# 输出: 42
```

### 访问浏览器

```bash
browser-use python "print(browser.url)"
```

### 显示已定义变量

```bash
browser-use python --vars
```

### 清除命名空间

```bash
browser-use python --reset
```

### 运行 Python 文件

```bash
browser-use python --file script.py
```

### 完整示例

```bash
browser-use open https://example.com

browser-use python "
for i in range(5):
    browser.scroll('down')
    browser.wait(0.5)
browser.screenshot('scrolled.png')
"
```

---

## 实用技巧

### 技巧 1：操作前确认

```bash
# 1. 获取状态
browser-use state

# 2. 截图
browser-use screenshot before.png

# 3. 操作
browser-use click 5

# 4. 验证
browser-use screenshot after.png
```

### 技巧 2：批量获取信息

```bash
# 获取所有链接
browser-use eval "
Array.from(document.querySelectorAll('a'))
  .map(a => ({text: a.textContent, href: a.href}))
"
```

### 技巧 3：表单验证

```bash
# 填写后验证值
browser-use input 0 "test@example.com"
browser-use get value 0
# 应输出: test@example.com
```

---

## 故障排除

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `Element not found` | 索引错误或元素未加载 | 重新运行 `state` 获取最新索引 |
| `Click no effect` | 元素被覆盖或不可点击 | 使用 `wait` 等待元素稳定 |
| `Type failed` | 元素未聚焦 | 先 `click` 元素或使用 `input` |
| `Screenshot failed` | 路径问题 | 使用绝对路径或检查目录权限 |
| `Eval timeout` | JS 执行超时 | 简化代码或分页处理 |

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `state` | 获取页面状态（元素索引） |
| `screenshot [path]` | 截图 |
| `click <index>` | 点击元素 |
| `dblclick <index>` | 双击元素 |
| `rightclick <index>` | 右键点击 |
| `hover <index>` | 悬停元素 |
| `type "text"` | 在聚焦元素输入 |
| `input <index> "text"` | 点击并输入 |
| `keys "key"` | 按键 |
| `select <index> "value"` | 下拉选择 |
| `upload <index> <path>` | 上传文件 |
| `get text <index>` | 获取元素文本 |
| `get value <index>` | 获取输入值 |
| `get attributes <index>` | 获取元素属性 |
| `get bbox <index>` | 获取元素位置 |
| `eval "js"` | 执行 JavaScript |
| `wait selector "css"` | 等待元素 |
| `python "code"` | 执行 Python |
