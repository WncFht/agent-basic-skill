---
name: tauri-devtools-mobile
description: Tauri 移动应用调试指南。用于 Android 和 iOS 移动应用的调试，包括设备列表、日志读取和移动 Session 管理。
---

# 移动开发

Tauri 移动应用（Android/iOS）的调试支持。

---

## 列出设备

查看可用的 Android 设备和 iOS 模拟器。

```bash
tauri-mcp list-devices
```

**输出示例：**
```
Android Devices:
  - emulator-5554 (Pixel 7 API 34)
  - 192.168.1.100:5555 (Physical Device)

iOS Booted Simulators:
  - iPhone 15 Pro (17.2) - UUID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  - iPad Pro (17.2) - UUID: yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
```

---

## Android 调试

### 读取 Logcat

```bash
# 读取最近 50 条日志
tauri-mcp read-logs --source android --lines 50

# 过滤特定标签
tauri-mcp read-logs --source android --filter "Tauri"
```

---

## iOS 调试

### 读取模拟器日志

```bash
# 读取最近 50 条日志
tauri-mcp read-logs --source ios --lines 50
```

---

## 移动应用 Session

对于移动应用，端口可能不同：

```bash
# Android 模拟器
tauri-mcp driver-session start --port 9223

# iOS 模拟器（可能需要不同端口）
tauri-mcp driver-session start --port 9000
```

---

## 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 设备未列出 | 模拟器未启动 | 启动 Android/iOS 模拟器 |
| 无法连接 | 网络问题 | 确保设备和电脑在同一网络 |
| 日志为空 | 应用未运行 | 确保应用已在设备上启动 |

---

## 参考

- [Tauri Mobile 文档](https://tauri.app/start/guides/what-is-tauri/)
- [Android Debug Bridge (ADB)](https://developer.android.com/studio/command-line/adb)
