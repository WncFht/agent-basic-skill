---
name: tauri-devtools-logs
description: Tauri 应用日志分析指南。用于读取控制台日志（JavaScript）、系统日志、Android logcat 和 iOS 模拟器日志。
---

# 日志分析

读取应用运行时的各类日志。

---

## 控制台日志

读取 WebView 的 JavaScript 控制台输出（console.log、error、warn 等）。

```bash
# 读取最近 20 条日志
tauri-mcp read-logs --source console --lines 20

# 过滤特定关键词
tauri-mcp read-logs --source console --filter "error"

# 读取从某个时间点开始的日志
tauri-mcp read-logs --source console --since "2024-01-01T00:00:00Z"
```

**输出示例：**
```
[ 2026-03-20T20:17:02.029Z ] [ LOG ] [MCP][BRIDGE][INFO] Console capture initialized
[ 2026-03-20T20:17:02.329Z ] [ DEBUG ] [vite] connected.
[ 2026-03-20T20:17:02.604Z ] [ LOG ] [API] Base URL: http://localhost:3000/api
[ 2026-03-20T20:17:02.774Z ] [ ERROR ] Get user error: {"name":"AuthSessionMissingError"}
[ 2026-03-20T20:17:02.825Z ] [ WARN ] MUI: You have provided an out-of-range value
```

**日志级别：**
- `[ LOG ]` - console.log
- `[ DEBUG ]` - console.debug
- `[ INFO ]` - console.info
- `[ WARN ]` - console.warn
- `[ ERROR ]` - console.error

---

## 系统日志

读取操作系统级别的日志（macOS 系统日志）。

```bash
# 读取最近 10 条系统日志
tauri-mcp read-logs --source system --lines 10
```

**输出示例：**
```
2026-03-21 04:18:57.691537+0800  localhost kernel[0]: (Sandbox) [com.apple.sandbox.reporting:violation] Sandbox: logd_helper(15377) deny(1) file-read-data ...
```

**使用场景：**
- 检查权限问题（Sandbox violations）
- 查看系统级错误

---

## 其他日志源

```bash
# Android logcat（仅移动应用）
tauri-mcp read-logs --source android --lines 50

# iOS 模拟器日志（仅移动应用）
tauri-mcp read-logs --source ios --lines 50
```

---

## 实用技巧

### 技巧 1：实时监控日志

```bash
# 循环读取新日志
while true; do
  tauri-mcp read-logs --source console --lines 5
  sleep 2
done
```

### 技巧 2：查找错误

```bash
# 过滤 ERROR 级别日志
tauri-mcp read-logs --source console --lines 100 | grep "ERROR"
```

### 技巧 3：配合操作

```bash
# 1. 记录当前日志行数
# 2. 执行某个操作
tauri-mcp webview-interact --action click --selector "#test-btn"

# 3. 查看新产生的日志
tauri-mcp read-logs --source console --lines 10
```

---

## 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `Failed to get console logs` | `withGlobalTauri` 未启用 | [查看初始化配置](../setup/SETUP.md) |
| 日志为空 | 控制台没有输出 | 检查前端代码是否有 console.log |
| 日志不更新 | 控制台捕获未初始化 | 刷新页面或重启应用 |
