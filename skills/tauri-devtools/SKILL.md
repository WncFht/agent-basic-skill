---
name: tauri-devtools
description: "用于调试 Tauri 应用的 MCP 工具集，提供截图、DOM 检查、元素交互、IPC 监控等功能。Use when working with Tauri applications for: (1) Debugging UI issues with screenshots and DOM inspection, (2) Automating UI interactions like clicks and input, (3) Monitoring IPC communication between frontend and backend, (4) Managing Tauri windows and sessions, (5) Reading console and system logs."
---

# Tauri DevTools

用于调试 Tauri 应用的 MCP 工具集，提供截图、DOM 检查、元素交互、IPC 监控等功能。

## 快速开始

### 第一步：检查环境

```bash
# 检查是否安装了 tauri-mcp-cli
tauri-mcp --version

# 检查 Tauri 应用是否在运行（端口 9223）
lsof -i :9223
```

### 第二步：连接应用

```bash
# 启动 driver session
tauri-mcp driver-session start --port 9223

# 验证连接
tauri-mcp driver-session status
```

### 第三步：基础调试

```bash
# 截图查看当前状态
tauri-mcp webview-screenshot --file debug.png

# 获取 DOM 结构
tauri-mcp webview-dom-snapshot --type accessibility

# 查看控制台日志
tauri-mcp read-logs --source console --lines 20
```

---

## 📚 完整功能目录

> 以下功能按类别组织，点击链接查看详细用法。

### 🔧 [初始化配置](./setup/SETUP.md)

**新项目的必要配置** - 如果这是你第一次在这个 Tauri 项目中使用 MCP Debug，请先看这里。

包含：
- MCP Bridge 插件安装
- `withGlobalTauri` 配置
- 权限配置
- 前端辅助函数注入

---

### 🔌 [Session 管理](./session/SESSION.md)

管理与 Tauri 应用的连接会话。

**常用命令：**
```bash
tauri-mcp driver-session start --port 9223
tauri-mcp driver-session status
tauri-mcp driver-session stop
```

---

### 🎯 [UI 自动化](./ui-automation/UI_AUTOMATION.md)

最强大的调试功能集合：截图、DOM 检查、元素查找与交互。

**功能列表：**
- 📸 网页截图
- 🌲 DOM Snapshot (accessibility/structure)
- 🔍 元素查找 (CSS/XPath/ref ID)
- 🎨 获取计算样式
- 👆 点击/聚焦/交互
- ⌨️ 键盘输入
- ⏱️ 等待元素
- 📜 JavaScript 执行

---

### 🪟 [窗口管理](./window/WINDOW.md)

管理应用窗口（多窗口支持）。

**功能列表：**
- 列出所有窗口
- 获取窗口信息
- 调整窗口大小

---

### ⚡ [IPC 调试](./ipc/IPC.md)

监控和调试 Tauri 的 IPC 通信。

**功能列表：**
- 获取后端状态
- 执行 IPC 命令
- 监控 IPC 调用
- 发送测试事件

---

### 📝 [日志分析](./logs/LOGS.md)

读取应用运行时日志。

**功能列表：**
- 读取控制台日志 (JavaScript)
- 读取系统日志

---

### 📱 [移动开发](./mobile/MOBILE.md)

移动端调试支持。

**功能列表：**
- 列出 Android 设备
- 列出 iOS 模拟器

---

## 典型调试工作流

### 场景 1：检查 UI 问题

```bash
# 1. 截图看当前状态
tauri-mcp webview-screenshot --file issue.png

# 2. 获取 DOM 看结构
tauri-mcp webview-dom-snapshot --type accessibility

# 3. 查看控制台是否有报错
tauri-mcp read-logs --source console --lines 50
```

### 场景 2：测试交互

```bash
# 1. 先截图确认初始状态
tauri-mcp webview-screenshot --file before.png

# 2. 点击某个元素
tauri-mcp webview-interact --action click --selector "#submit-btn"

# 3. 截图看结果
tauri-mcp webview-screenshot --file after.png
```

### 场景 3：调试 IPC 问题

```bash
# 1. 启动 IPC 监控
tauri-mcp ipc-monitor --action start

# 2. 在应用中触发操作

# 3. 查看捕获的 IPC 调用
tauri-mcp ipc-get-captured

# 4. 停止监控
tauri-mcp ipc-monitor --action stop
```

---

## 故障排除

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| `no Tauri app found` | MCP Bridge 未安装 | [查看初始化配置](./setup/SETUP.md) |
| `Script execution timeout` | `withGlobalTauri` 未启用 | [查看初始化配置](./setup/SETUP.md) |
| `resolveRef is not a function` | 前端辅助函数未注入 | [查看初始化配置](./setup/SETUP.md) |
| `Connection refused` | 端口错误或应用未启动 | 检查 `lsof -i :9223` |
| `No active session` | Session 已断开 | 重新运行 `driver-session start` |

---

## 参考

- [MCP Server Tauri 官方文档](https://github.com/hypothesi/mcp-server-tauri)
- [Tauri 官方文档](https://tauri.app)
