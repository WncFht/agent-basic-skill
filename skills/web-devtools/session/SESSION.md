---
name: web-devtools-session
description: Browser Use 会话管理指南。管理浏览器会话和守护进程，包括列出活跃会话、关闭会话、多会话管理和故障排除。
---

# 会话管理

管理浏览器会话和守护进程。

---

## 会话架构

Browser Use CLI 使用多会话守护进程架构：

1. **首次命令** - 为该会话启动后台守护进程（浏览器保持打开）
2. **后续命令** - 通过 Unix Socket（macOS/Linux）或 TCP（Windows）通信
3. **浏览器持久化** - 跨命令保持浏览器打开，实现快速交互（~50ms 延迟）
4. **多会话支持** - 每个 `--session` 有独立的守护进程、Socket 和 PID 文件
5. **自动管理** - 需要时自动启动，浏览器死亡时自动退出，或手动 `browser-use close` 停止

---

## 列出活跃会话

查看当前所有的浏览器会话：

```bash
browser-use sessions
```

**输出示例：**
```
SESSION   STATUS    BROWSER      URL
default   active    chromium     https://example.com
work      active    chrome       https://github.com
cloud     active    cloud        https://example.com
```

---

## 关闭会话

### 关闭当前会话

```bash
browser-use close
```

这会关闭当前会话的浏览器和守护进程。

### 关闭所有会话

```bash
browser-use close --all
```

一次性关闭所有活跃的会话。

### 关闭特定会话

```bash
browser-use --session work close
```

关闭名为 `work` 的会话。

---

## 多会话管理

### 默认会话

不指定 `--session` 时使用默认会话 `default`：

```bash
# 使用 default 会话
browser-use open https://example.com
browser-use state
```

### 命名会话

使用 `--session` 创建多个独立会话：

```bash
# 工作会话
browser-use --session work open https://github.com
browser-use --session work state

# 个人会话
browser-use --session personal open https://gmail.com
browser-use --session personal state

# 云浏览器会话
browser-use --session cloud cloud connect
```

### 环境变量配置

通过环境变量设置默认会话：

```bash
export BROWSER_USE_SESSION=work
browser-use state  # 自动使用 work 会话
```

---

## 文件布局

所有 CLI 管理的文件位于 `~/.browser-use/`（可用 `BROWSER_USE_HOME` 覆盖）：

```
~/.browser-use/
├── config.json          # API key, 设置 (与 profile-use 共享)
├── bin/
│   └── profile-use      # 管理的 Go 二进制 (自动下载)
├── tunnels/
│   ├── {port}.json      # 隧道元数据
│   └── {port}.log       # 隧道日志
├── default.sock         # 守护进程 Socket (临时)
├── default.pid          # 守护进程 PID (临时)
├── work.sock            # 命名会话 Socket
├── work.pid             # 命名会话 PID
└── cli.log              # 守护进程日志
```

---

## 故障排除

### 问题 1：No active session

**症状：**
```
Error: No active session
```

**原因：**
- 守护进程未运行
- 会话已过期
- 浏览器崩溃

**解决方案：**
```bash
# 1. 检查活跃会话
browser-use sessions

# 2. 重新打开浏览器
browser-use open https://example.com

# 3. 或重启守护进程
browser-use close --all
browser-use open https://example.com
```

### 问题 2：Failed to start daemon

**症状：**
```
Failed to start daemon
```

**原因：**
- 僵尸进程占用资源
- 端口冲突
- 权限问题

**解决方案：**

**macOS/Linux:**
```bash
# 查找僵尸进程
ps aux | grep browser-use

# 杀死进程
kill -9 <pid>

# 或删除 PID 文件
rm ~/.browser-use/*.pid
rm ~/.browser-use/*.sock
```

**Windows:**
```powershell
# 查找进程
wmic process where "name='python.exe' and commandline like '%browser%use%'" get processid

# 杀死进程
taskkill /PID <pid> /F

# 删除虚拟环境重新安装
Remove-Item -Recurse -Force "$env:USERPROFILE\.browser-use-env"
```

### 问题 3：Session 冲突

**症状：**
多个命令同时操作同一会话导致冲突。

**解决方案：**
```bash
# 使用不同会话
browser-use --session task1 open https://site1.com
browser-use --session task2 open https://site2.com

# 分别操作
browser-use --session task1 state
browser-use --session task2 state
```

---

## 典型工作流

### 场景 1：并行任务

```bash
# 任务 1: 监控网站
browser-use --session monitor open https://status.example.com

# 任务 2: 自动化操作
browser-use --session automation open https://app.example.com

# 分别操作
browser-use --session monitor screenshot status.png
browser-use --session automation click 5
```

### 场景 2：切换会话

```bash
# 列出会话
browser-use sessions

# 切换 work 会话
browser-use --session work state

# 切换回 default
browser-use state
```

### 场景 3：清理会话

```bash
# 关闭特定会话
browser-use --session old-task close

# 或关闭所有
browser-use close --all
```

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `browser-use sessions` | 列出活跃会话 |
| `browser-use close` | 关闭当前会话 |
| `browser-use close --all` | 关闭所有会话 |
| `browser-use --session NAME` | 指定会话操作 |
