---
name: web-devtools-cloud
description: Browser Use 云平台使用指南。提供云端浏览器连接、API 认证、API v2/v3 调用和任务管理功能。
---

# 云平台

Browser Use 云平台功能，提供云端浏览器和 API 管理。

---

## 认证

### 登录

保存 API Key：

```bash
browser-use cloud login sk-your-api-key
```

或使用环境变量：
```bash
export BROWSER_USE_API_KEY=sk-your-api-key
```

API Key 保存在 `~/.browser-use/config.json`（权限 0600）。

### 登出

```bash
browser-use cloud logout
```

---

## 云端浏览器

### 连接云端浏览器

```bash
# 基础连接
browser-use cloud connect

# 带超时连接（秒）
browser-use cloud connect --timeout 120

# 使用代理
browser-use cloud connect --proxy-country US

# 使用 Profile
browser-use cloud connect --profile-id <id>
```

**说明：**
- 连接后，所有命令正常工作
- `close` 会断开并停止云端浏览器
- 云端浏览器在云端运行，不受本地资源限制

---

## API 调用

### API v2

```bash
# GET 请求
browser-use cloud v2 GET /browsers

# POST 请求
browser-use cloud v2 POST /tasks '{"task":"Search for AI news","url":"https://google.com"}'
```

### API v3

```bash
browser-use cloud v3 POST /endpoint '{"key":"value"}'
```

### 轮询任务

```bash
# 轮询任务直到完成
browser-use cloud v2 poll <task-id>
```

### 查看 API 端点

```bash
# 查看 v2 端点
browser-use cloud v2 --help

# 查看 v3 端点
browser-use cloud v3 --help
```

---

## 典型工作流

### 场景 1：云端自动化

```bash
# 1. 登录
browser-use cloud login sk-abc123...

# 2. 连接云端浏览器
browser-use cloud connect

# 3. 正常使用
browser-use open https://example.com
browser-use state
browser-use screenshot cloud.png

# 4. 关闭（停止云端浏览器）
browser-use close
```

### 场景 2：创建任务

```bash
# 1. 登录
browser-use cloud login sk-abc123...

# 2. 创建任务
browser-use cloud v2 POST /tasks '{
  "task": "Search for AI news",
  "url": "https://google.com"
}'

# 3. 轮询任务状态
browser-use cloud v2 poll <task-id>

# 4. 获取结果
browser-use cloud v2 GET /tasks/<task-id>
```

### 场景 3：列出浏览器

```bash
browser-use cloud v2 GET /browsers
```

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `cloud login <key>` | 保存 API Key |
| `cloud logout` | 移除 API Key |
| `cloud connect` | 连接云端浏览器 |
| `cloud v2 GET <path>` | API v2 GET |
| `cloud v2 POST <path> '<json>'` | API v2 POST |
| `cloud v3 POST <path> '<json>'` | API v3 POST |
| `cloud v2 poll <id>` | 轮询任务 |
| `cloud v2 --help` | 查看 v2 端点 |
| `cloud v3 --help` | 查看 v3 端点 |
