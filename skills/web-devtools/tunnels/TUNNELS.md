---
name: web-devtools-tunnels
description: Browser Use 隧道管理指南。将本地开发服务器暴露给云端浏览器，包括创建隧道、列出隧道和停止隧道。
---

# 隧道

将本地开发服务器暴露给云端浏览器。

---

## 创建隧道

启动隧道并获取公共 URL：

```bash
browser-use tunnel <port>
```

**示例：**
```bash
# 为 localhost:3000 创建隧道
browser-use tunnel 3000

# 输出: https://abc.trycloudflare.com
```

---

## 列出隧道

查看所有活跃的隧道：

```bash
browser-use tunnel list
```

**输出示例：**
```
PORT  URL                         STATUS
3000  https://abc.trycloudflare.com  active
8080  https://xyz.trycloudflare.com  active
```

---

## 停止隧道

### 停止特定端口

```bash
browser-use tunnel stop 3000
```

### 停止所有隧道

```bash
browser-use tunnel stop --all
```

---

## 典型工作流

### 场景：本地开发测试

```bash
# 1. 启动本地开发服务器
npm run dev &
# 输出: localhost:3000

# 2. 创建隧道
browser-use tunnel 3000
# 输出: https://abc.trycloudflare.com

# 3. 连接云端浏览器
browser-use cloud connect

# 4. 访问本地服务
browser-use open https://abc.trycloudflare.com

# 5. 正常使用
browser-use state
browser-use screenshot local-test.png

# 6. 清理
browser-use close
browser-use tunnel stop 3000
```

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `tunnel <port>` | 创建隧道 |
| `tunnel list` | 列出隧道 |
| `tunnel stop <port>` | 停止隧道 |
| `tunnel stop --all` | 停止所有隧道 |
