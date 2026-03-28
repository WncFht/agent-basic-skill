---
name: tauri-devtools-window
description: Tauri 应用窗口管理指南。用于管理多窗口应用，包括列出窗口、获取窗口信息和调整窗口大小。
---

# 窗口管理

管理 Tauri 应用窗口（支持多窗口应用）。

---

## 列出所有窗口

```bash
tauri-mcp manage-window --action list
```

**输出示例：**
```json
{
  "windows": [
    {
      "label": "main",
      "title": "龙虾孵化器 - OpenClaw 安装器",
      "url": "http://localhost:5173/",
      "visible": true,
      "focused": true,
      "isMain": true
    }
  ],
  "defaultWindow": "main",
  "totalCount": 1
}
```

---

## 获取窗口详细信息

```bash
tauri-mcp manage-window --action info

# 指定窗口（多窗口应用）
tauri-mcp manage-window --action info --window-id "secondary"
```

**输出示例：**
```json
{
  "title": "龙虾孵化器 - OpenClaw 安装器",
  "width": 2200,
  "height": 1500,
  "x": 610,
  "y": 184,
  "focused": true,
  "visible": true
}
```

---

## 调整窗口大小

```bash
# 调整主窗口
tauri-mcp manage-window --action resize --width 1200 --height 800

# 调整特定窗口
tauri-mcp manage-window --action resize --width 1920 --height 1080 --window-id "secondary"
```

**参数：**
- `--width`：宽度（逻辑像素）
- `--height`：高度（逻辑像素）
- `--window-id`：窗口标签（可选，默认主窗口）

---

## 多窗口应用示例

```bash
# 1. 查看所有窗口
tauri-mcp manage-window --action list

# 2. 在 secondary 窗口执行操作
tauri-mcp webview-screenshot --file popup.png --window-id "secondary"
tauri-mcp webview-interact --action click --selector "#close" --window-id "secondary"

# 3. 调整副窗口大小
tauri-mcp manage-window --action resize --width 800 --height 600 --window-id "secondary"
```

---

## 使用场景

- **响应式测试**：调整窗口大小测试不同分辨率
- **多窗口应用**：管理和操作多个窗口
- **自动化测试**：确保窗口在预期状态
