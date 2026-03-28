---
name: web-devtools-setup
description: Web DevTools 初始化配置指南。首次使用 Web DevTools 时必须完成的配置，包括安装 Browser Use CLI、安装 Chromium 和验证安装。
---

# Web DevTools - 初始化配置

> ⚠️ **这是必看文档**  
> 如果你是第一次使用 Web DevTools，必须完成以下配置。

---

## 安装 Browser Use CLI

### 前置要求

| 平台 | 要求 |
|------|------|
| **macOS** | Python 3.11+ (安装器会自动使用 Homebrew) |
| **Linux** | Python 3.11+ (安装器会自动使用 apt) |
| **Windows** | Git for Windows, Python 3.11+ |

### 一键安装（推荐）

**macOS / Linux:**
```bash
curl -fsSL https://browser-use.com/cli/install.sh | bash
```

**Windows** (PowerShell 中运行):
```powershell
& "C:\Program Files\Git\bin\bash.exe" -c 'curl -fsSL https://browser-use.com/cli/install.sh | bash'
```

### 手动安装

如果你不想使用一键安装脚本：

```bash
# 1. 安装包
uv pip install browser-use

# 2. 安装 Chromium
browser-use install

# 3. 验证安装
browser-use doctor
```

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/browser-use/browser-use.git
cd browser-use

# 安装
pip install -e .
```

---

## 安装后验证

### 验证安装

```bash
browser-use doctor
```

**成功输出示例：**
```
✓ browser-use 已安装 (v0.x.x)
✓ Chromium 已安装
✓ 守护进程可启动
```

### 运行设置向导（可选）

```bash
browser-use setup
```

---

## 安装 Skill（推荐）

CLI 配合 Skill 使用更强大：

```bash
npx skills add https://github.com/browser-use/browser-use --skill browser-use
```

---

## 首次使用测试

```bash
# 1. 打开网页（会自动启动浏览器）
browser-use open https://example.com

# 2. 查看页面状态
browser-use state

# 3. 截图
browser-use screenshot test.png

# 4. 关闭浏览器
browser-use close
```

---

## 平台特定配置

### macOS

如果安装后命令找不到：

```bash
# 检查安装路径
which browser-use

# 如果没有输出，手动添加 PATH
export PATH="$HOME/.local/bin:$PATH"

# 永久添加到 ~/.zshrc 或 ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Linux

```bash
# Ubuntu/Debian 依赖
sudo apt-get install -y libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libpango-1.0-0 libcairo2 libasound2

# 添加 PATH
export PATH="$HOME/.local/bin:$PATH"
```

### Windows

**ARM64 Windows** (Surface Pro X, Snapdragon 笔记本):

需要安装 x64 Python（通过模拟器运行）：
```powershell
winget install Python.Python.3.11 --architecture x64
```

**多版本 Python:**

设置显式版本：
```powershell
# 使用特定版本
py -3.11 -m pip install browser-use
```

**PATH 不生效:**

重启终端后如果仍不工作：
```powershell
# 检查 PATH
echo $env:PATH

# 或使用 Git Bash
& "C:\Program Files\Git\bin\bash.exe" -c 'browser-use --help'
```

---

## 常见问题

**Q: 安装后提示 `command not found`?**  
A: 需要添加 PATH。检查 `~/.local/bin` 或 `pip show browser-use` 查看安装位置。

**Q: `Failed to start browser` 错误?**  
A: Chromium 未安装，运行 `browser-use install` 安装。

**Q: 如何更新 CLI?**  
A: 
```bash
pip install --upgrade browser-use
```

**Q: 如何完全卸载?**  
A:
```bash
pip uninstall browser-use
rm -rf ~/.browser-use
```

**Q: Windows 提示 `Failed to start daemon`?**  
A: 可能有僵尸进程，杀死它们：
```powershell
# 查找进程
wmic process where "name='python.exe' and commandline like '%browser%use%'" get processid

# 杀死进程
taskkill /PID <pid> /F

# 或删除虚拟环境重新安装
Remove-Item -Recurse -Force "$env:USERPROFILE\.browser-use-env"
```

---

## 验证配置清单

- [ ] 安装 browser-use CLI
- [ ] 安装 Chromium (`browser-use install`)
- [ ] 运行 `browser-use doctor` 验证
- [ ] 运行 `browser-use open https://example.com` 测试
- [ ] 运行 `browser-use state` 查看元素
- [ ] 运行 `browser-use close` 关闭
