---
name: web-devtools-navigation
description: Web 页面导航指南。提供网页导航、滚动、标签页管理和 Cookie 管理功能，包括前进后退、滚动页面、切换标签页和 Cookie 导入导出。
---

# 页面导航

网页导航、滚动和 Cookie 管理。

---

## 🌐 URL 导航

### 打开网页

```bash
# 基础打开
browser-use open https://example.com

# 带模式打开
browser-use --headed open https://example.com  # 可视模式
```

### 前进/后退

```bash
# 后退
browser-use back

# 注意：前进功能未直接提供，可通过 open 重新导航
```

---

## 📜 滚动页面

### 向下滚动

```bash
# 默认滚动
browser-use scroll down

# 指定像素滚动
browser-use scroll down --amount 1000
```

### 向上滚动

```bash
browser-use scroll up
browser-use scroll up --amount 500
```

---

## 📑 标签页管理

### 切换标签页

```bash
# 按索引切换标签页
browser-use switch 1
```

### 关闭标签页

```bash
# 关闭当前标签页
browser-use close-tab

# 关闭指定标签页
browser-use close-tab 2
```

---

## 🍪 Cookie 管理

### 获取所有 Cookie

```bash
browser-use cookies get
```

### 获取特定 URL 的 Cookie

```bash
browser-use cookies get --url https://example.com
```

### 设置 Cookie

```bash
# 基础设置
browser-use cookies set session_id abc123

# 带选项设置
browser-use cookies set name value --domain .example.com --secure
browser-use cookies set name value --same-site Strict
browser-use cookies set name value --expires 1735689600
```

**选项说明：**
- `--domain`: Cookie 适用的域名（如 `.example.com`）
- `--secure`: 仅 HTTPS 传输
- `--same-site`: SameSite 属性（Strict, Lax, None）
- `--expires`: 过期时间戳（Unix 时间戳）

### 清除 Cookie

```bash
# 清除所有 Cookie
browser-use cookies clear

# 清除特定 URL 的 Cookie
browser-use cookies clear --url https://example.com
```

### 导出/导入 Cookie

```bash
# 导出到文件
browser-use cookies export cookies.json

# 从文件导入
browser-use cookies import cookies.json
```

---

## 📄 获取页面信息

### 获取标题

```bash
browser-use get title
```

### 获取完整 HTML

```bash
browser-use get html
```

### 获取元素 HTML

```bash
browser-use get html --selector "h1"
```

---

## 典型工作流

### 场景 1：保持登录态

```bash
# 1. 登录（手动或自动化）
browser-use open https://example.com/login
browser-use input 0 "user@example.com"
browser-use input 1 "password"
browser-use click 2

# 2. 导出 Cookie
browser-use cookies export auth.json

# 3. 下次使用导入
browser-use open https://example.com
browser-use cookies import auth.json
```

### 场景 2：多标签页操作

```bash
# 打开第一个页面
browser-use open https://example.com/page1

# 打开新标签（通过页面操作）
browser-use click 5  # 假设是 "Open in new tab" 链接

# 查看所有标签
browser-use sessions

# 切换标签
browser-use switch 1

# 操作第二个标签
browser-use state

# 关闭第二个标签
browser-use close-tab
```

### 场景 3：滚动加载

```bash
# 打开页面
browser-use open https://example.com/infinite-scroll

# 多次滚动加载内容
for i in {1..5}; do
  browser-use scroll down --amount 800
  sleep 1
done

# 截图查看
browser-use screenshot loaded.png
```

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `open <url>` | 打开网页 |
| `back` | 后退 |
| `scroll down` | 向下滚动 |
| `scroll up` | 向上滚动 |
| `switch <tab>` | 切换标签页 |
| `close-tab` | 关闭标签页 |
| `cookies get` | 获取 Cookie |
| `cookies set` | 设置 Cookie |
| `cookies clear` | 清除 Cookie |
| `cookies export` | 导出 Cookie |
| `cookies import` | 导入 Cookie |
| `get title` | 获取页面标题 |
| `get html` | 获取页面 HTML |
