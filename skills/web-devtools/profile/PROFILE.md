---
name: web-devtools-profile
description: Browser Use Profile 管理指南。将浏览器 Profile 同步到云端，包括列出 Profiles、同步 Profile 和检查 Cookie。
---

# Profile 管理

浏览器 Profile 同步到 Browser Use 云端。

`profile` 子命令委托给 `profile-use` Go 二进制文件，它同步本地浏览器 Cookie 到 Browser Use 云。

二进制文件管理在 `~/.browser-use/bin/profile-use`，首次使用时自动下载。

---

## 交互式向导

启动交互式同步向导：

```bash
browser-use profile
```

---

## 列出 Profiles

查看检测到的浏览器和 Profiles：

```bash
browser-use profile list
```

**输出示例：**
```
BROWSER         PROFILE
Google Chrome   Default
Google Chrome   Profile 1
Microsoft Edge  Default
```

---

## 同步 Profile

### 同步所有 Profiles

```bash
browser-use profile sync --all
```

### 同步特定 Profile

```bash
browser-use profile sync \
  --browser "Google Chrome" \
  --profile "Default"
```

---

## 设置 API Key

```bash
browser-use profile auth --apikey <key>
```

**注意：** 与 `cloud login` 共享 API Key。

---

## 本地检查 Cookie

```bash
browser-use profile inspect \
  --browser "Google Chrome" \
  --profile "Default"
```

---

## 更新 Binary

下载/更新 `profile-use` 二进制：

```bash
browser-use profile update
```

---

## 典型工作流

### 场景：同步登录态

```bash
# 1. 设置 API Key
browser-use profile auth --apikey sk-abc123...

# 2. 列出可用 Profiles
browser-use profile list

# 3. 同步 Default Profile
browser-use profile sync \
  --browser "Google Chrome" \
  --profile "Default"

# 4. 云端使用
browser-use cloud connect
browser-use open https://gmail.com  # 已登录
```

---

## 命令速查表

| 命令 | 作用 |
|------|------|
| `profile` | 交互式向导 |
| `profile list` | 列出 Profiles |
| `profile sync --all` | 同步所有 Profiles |
| `profile sync --browser X --profile Y` | 同步特定 Profile |
| `profile auth --apikey <key>` | 设置 API Key |
| `profile inspect` | 本地检查 Cookie |
| `profile update` | 更新 Binary |
