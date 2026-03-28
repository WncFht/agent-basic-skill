---
name: tauri-devtools-session
description: Tauri 应用 Session 连接管理。管理与应用连接的会话，包括启动、查看状态、停止 Session 以及 Daemon 管理。
---

# Session 管理

管理与 Tauri 应用的连接会话。所有其他工具都依赖活跃的 Session。

---

## 命令

### 启动 Session

```bash
tauri-mcp driver-session start --port 9223
```

**参数：**
- `--port 9223`：MCP Bridge 监听端口（默认 9223）

**成功输出：**
```
Session started with app: Tauri App (localhost:9223) (localhost:9223) [DEFAULT]
```

**失败情况：**
- `no Tauri app found` → 检查应用是否运行，或 [查看初始化配置](../setup/SETUP.md)

---

### 查看 Session 状态

```bash
tauri-mcp driver-session status
```

**输出示例：**
```json
{
  "connected": true,
  "app": "Tauri App (localhost:9223)",
  "identifier": "com.example.app",
  "host": "localhost",
  "port": 9223
}
```

---

### 停止 Session

```bash
tauri-mcp driver-session stop
```

**输出：**
```
All sessions stopped
```

---

## Daemon 管理（高级）

CLI 使用 keep-alive daemon 维持状态：

```bash
# 查看 daemon 状态
tauri-mcp daemon status

# 重启 daemon（解决奇怪问题）
tauri-mcp daemon restart

# 停止 daemon
tauri-mcp daemon stop
```

---

## 典型工作流

```bash
# 1. 确保应用已启动，然后连接
tauri-mcp driver-session start --port 9223

# 2. 验证连接
tauri-mcp driver-session status

# 3. 执行其他调试操作...

# 4. 完成后断开
tauri-mcp driver-session stop
```

---

## 故障排除

| 问题 | 解决方案 |
|------|---------|
| `Connection refused` | 应用未启动，或端口错误 |
| `No active session` | Session 已过期，重新 `start` |
| `Stale daemon` | 运行 `tauri-mcp daemon restart` |
