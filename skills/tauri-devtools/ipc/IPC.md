---
name: tauri-devtools-ipc
description: Tauri IPC 通信调试指南。用于监控和调试前后端通信，包括获取后端状态、执行 IPC 命令、监控 IPC 调用和发送测试事件。
---

# IPC 调试

监控和调试 Tauri 的前后端通信（IPC）。

---

## 获取后端状态

获取 Tauri 应用的基本信息。

```bash
tauri-mcp ipc-get-backend-state
```

**输出示例：**
```json
{
  "app": {
    "identifier": "com.clawegg.desktop",
    "name": "龙虾孵化器",
    "version": "0.1.0"
  },
  "environment": {
    "arch": "aarch64",
    "debug": true,
    "family": "unix",
    "os": "macos"
  },
  "tauri": {
    "version": "2.10.3"
  },
  "window_count": 1
}
```

---

## 执行 IPC 命令

直接调用 Tauri 后端命令。

```bash
# 调用自定义命令
tauri-mcp ipc-execute-command --command "get_system_info"

# 带参数调用
tauri-mcp ipc-execute-command --command "save_config" --args '{"key": "value"}'
```

**注意：** 命令必须在 Rust 代码中已注册：
```rust
.invoke_handler(tauri::generate_handler![get_system_info, save_config])
```

**错误示例：**
```json
{"success":false,"error":"Unsupported Tauri command: xxx"}
```

---

## 监控 IPC 调用

实时监控所有 IPC 通信（前端调用后端、后端响应）。

### 启动监控

```bash
tauri-mcp ipc-monitor --action start
```

**输出：**
```
"IPC monitoring started"
```

### 查看捕获的调用

```bash
# 查看所有捕获的 IPC 事件
tauri-mcp ipc-get-captured
```

**输出示例：**
```json
[
  {
    "timestamp": 1234567890,
    "command": "get_system_info",
    "args": {},
    "result": {...},
    "durationMs": 5
  }
]
```

### 停止监控

```bash
tauri-mcp ipc-monitor --action stop
```

---

## 发送测试事件

向后端发送自定义事件（用于测试事件处理器）。

```bash
tauri-mcp ipc-emit-event --event-name "user-logged-in" --payload '{"userId": 123}'
```

---

## 典型调试工作流

### 调试 IPC 问题

```bash
# 1. 启动监控
tauri-mcp ipc-monitor --action start

# 2. 在应用中触发操作（如点击按钮调用后端）

# 3. 查看捕获的调用
tauri-mcp ipc-get-captured

# 4. 分析请求参数和响应结果

# 5. 停止监控
tauri-mcp ipc-monitor --action stop
```

### 验证后端命令

```bash
# 直接调用命令验证是否正常工作
tauri-mcp ipc-execute-command --command "check_environment"
```

---

## 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `Unsupported Tauri command` | 命令未注册 | 检查 Rust 代码中的 `generate_handler` |
| 监控无数据 | 前端未触发 IPC | 检查前端代码是否调用了 `invoke` |
| `Request timeout` | 后端处理耗时过长 | 优化后端代码或增加超时时间 |
