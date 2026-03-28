---
name: web-devtools
description: "基于 browser-use CLI 的浏览器自动化调试工具集，提供网页控制、元素交互、截图、Cookie 管理、云端浏览器等功能。Use when working with web applications for: (1) Browser automation and UI testing, (2) Taking screenshots and inspecting page elements, (3) Filling forms and simulating user interactions, (4) Managing cookies and sessions, (5) Using cloud-based browsers for remote debugging, (6) Creating tunnels for local development servers."
---

# Web DevTools

基于 browser-use CLI 的浏览器自动化调试工具集，提供网页控制、元素交互、截图、Cookie 管理、云端浏览器等功能。

## 快速开始

### 第一步：检查安装

```bash
# 检查是否安装了 browser-use
browser-use doctor

# 查看版本
browser-use --version
```

### 第二步：基础调试

```bash
# 打开网页
browser-use open https://example.com

# 查看页面状态（含可点击元素索引）
browser-use state

# 截图
browser-use screenshot output.png

# 关闭浏览器
browser-use close
```

### 第三步：元素交互

```bash
# 打开网页
browser-use open https://example.com

# 查看元素索引
browser-use state
# 输出示例: [5] button "Submit"

# 点击元素
browser-use click 5

# 输入文本
browser-use type "Hello World"

# 关闭浏览器
browser-use close
```

---

## 📚 完整功能目录

> 以下功能按类别组织，点击链接查看详细用法。

### 🔧 [初始化配置](./setup/SETUP.md)

**新项目的必要配置** - 如果这是你第一次使用 Web DevTools，请先看这里。

包含：
- 安装 browser-use CLI
- 安装 Chromium
- 验证安装
- 多平台配置

---

### 🔌 [会话管理](./session/SESSION.md)

管理浏览器会话和守护进程。

**功能列表：**
- 列出活跃会话
- 关闭会话
- 多会话管理
- 环境变量配置

---

### 🎯 [UI 自动化](./ui-automation/UI_AUTOMATION.md)

核心调试功能：截图、元素检查、点击、输入、表单填写等。

**功能列表：**
- 📸 网页截图
- 🔍 获取页面状态（元素索引）
- 👆 点击/双击/右键/悬停元素
- ⌨️ 输入文本/按键
- 📋 获取元素信息（文本、属性、位置）
- 📝 表单填写
- 📤 文件上传
- ⏱️ 等待元素
- 📜 JavaScript 执行

---

### 🧭 [页面导航](./navigation/NAVIGATION.md)

网页导航和标签页管理。

**功能列表：**
- 打开/跳转 URL
- 前进/后退
- 滚动页面
- 标签页切换
- Cookie 管理

---

### ☁️ [云平台](./cloud/CLOUD.md)

Browser Use 云平台功能。

**功能列表：**
- 登录/登出
- 云端浏览器连接
- 任务管理
- API 调用

---

### 🌐 [隧道](./tunnels/TUNNELS.md)

将本地开发服务器暴露给云端浏览器。

**功能列表：**
- 创建隧道
- 列出隧道
- 停止隧道

---

### 👤 [Profile 管理](./profile/PROFILE.md)

浏览器 Profile 同步到云端。

**功能列表：**
- 列出浏览器 Profiles
- 同步 Profile
- 检查 Cookies

---

## 浏览器模式

| 模式 | 命令 | 说明 |
|------|------|------|
| **无头模式** (默认) | `browser-use open <url>` | 后台运行，速度最快 |
| **可视模式** | `browser-use --headed open <url>` | 显示浏览器窗口 |
| **真实 Chrome** | `browser-use --profile "Default" open <url>` | 使用已有登录态 |
| **连接现有** | `browser-use --connect open <url>` | 连接已运行的 Chrome |
| **CDP 连接** | `browser-use --cdp-url <url> open` | 通过 CDP URL 连接 |
| **云端浏览器** | `browser-use cloud connect` | 使用 Browser Use 云 |

---

## 典型调试工作流

### 场景 1：检查 UI 问题

```bash
# 1. 打开页面
browser-use open https://example.com

# 2. 截图查看
browser-use screenshot issue.png

# 3. 获取页面状态
browser-use state

# 4. 关闭浏览器
browser-use close
```

### 场景 2：表单自动化测试

```bash
# 1. 打开表单页面
browser-use open https://example.com/form

# 2. 查看元素索引
browser-use state

# 3. 填写表单
browser-use input 0 "John Doe"        # 姓名
browser-use input 1 "john@example.com" # 邮箱
browser-use select 2 "Option A"        # 下拉选择

# 4. 提交
browser-use click 5

# 5. 截图验证
browser-use screenshot result.png

# 6. 关闭
browser-use close
```

### 场景 3：云端浏览器调试

```bash
# 1. 登录
browser-use cloud login sk-your-api-key

# 2. 连接云端浏览器
browser-use cloud connect

# 3. 正常使用
browser-use open https://example.com
browser-use state
browser-use screenshot cloud.png

# 4. 关闭（同时停止云端浏览器）
browser-use close
```

---

## 故障排除

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| `command not found: browser-use` | 未安装 CLI | [查看初始化配置](./setup/SETUP.md) |
| `Failed to start browser` | Chromium 未安装 | 运行 `browser-use install` |
| `No active session` | 守护进程未运行 | 重新运行 `browser-use open` |
| 元素点击无效 | 元素未加载 | 使用 `wait selector` 等待 |
| 截图失败 | 路径问题 | 使用绝对路径或检查目录权限 |

---

## 参考

- [Browser Use 官方文档](https://docs.browser-use.com/)
- [Browser Use GitHub](https://github.com/browser-use/browser-use)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
