---
name: tauri-devtools-setup
description: Tauri MCP Debug 初始化配置指南。首次使用 Tauri DevTools 时必须完成的配置步骤，包括 MCP Bridge 插件安装、withGlobalTauri 配置、权限配置和前端辅助函数注入。
---

# Tauri MCP Debug - 初始化配置

> ⚠️ **这是必看文档**  
> 如果你是第一次在这个 Tauri 项目中使用 MCP Debug 工具，必须完成以下 4 步配置，否则大部分功能会失败。

---

## 踩坑记录（4 个必配项）

### 坑 1：未安装 MCP Bridge 插件

**错误表现：**
```
Session start failed - no Tauri app found at localhost or localhost:9223
```

**解决方案：**

1. 在 `src-tauri/Cargo.toml` 中添加依赖：
```toml
[dependencies]
tauri-plugin-mcp-bridge = "0.10"
```

2. 在 `src-tauri/src/lib.rs` 中初始化插件：
```rust
tauri::Builder::default()
    .plugin(tauri_plugin_mcp_bridge::init())  // 添加这一行
    // ... 其他配置
    .run(tauri::generate_context!())
```

---

### 坑 2：`withGlobalTauri` 未启用

**错误表现：**
- DOM Snapshot 超时
- JavaScript 执行超时
- 控制台日志读取超时

**解决方案：**

在 `src-tauri/tauri.conf.json` 中设置：
```json
{
  "app": {
    "withGlobalTauri": true
  }
}
```

> 没有这个设置，MCP Bridge 无法与 WebView 通信。

---

### 坑 3：缺少插件权限

**错误表现：**
- 部分工具返回权限错误
- 无法执行 IPC 命令

**解决方案：**

在 `src-tauri/capabilities/default.json` 中添加权限：
```json
{
  "permissions": [
    "core:default",
    // ... 其他权限
    "mcp-bridge:default"
  ]
}
```

---

### 坑 4：前端辅助函数未注入

**错误表现：**
```
window.__MCP__.resolveRef is not a function
window.__MCP__.countAll is not a function
```

**解决方案：**

在前端入口文件（如 `src/main.tsx` 或 `src/main.ts`）中添加：

```typescript
// MCP Bridge Helper Functions - 用于自动化测试支持
if (import.meta.env.DEV) {
  const injectMcpHelpers = () => {
    if (typeof window === 'undefined') return;
    
    (window as any).__MCP__ = (window as any).__MCP__ || {};
    
    // 解析单个元素
    (window as any).__MCP__.resolveRef = function(selector: string, strategy?: string): Element | null {
      if (!selector) return null;
      
      // 支持 ref ID (如 "e3", "ref=e3")
      const refMatch = selector.match(/^\[?(?:ref=)?(e\d+)\]?$/);
      if (refMatch) {
        const reverseRefs = (window as any).__MCP__.reverseRefs;
        if (!reverseRefs) {
          throw new Error('Ref IDs require a snapshot. Run webview_dom_snapshot first.');
        }
        return reverseRefs.get(refMatch[1]) || null;
      }
      
      // XPath
      if (strategy === 'xpath') {
        const result = document.evaluate(selector, document, null, 
          XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        return result.singleNodeValue as Element | null;
      }
      
      // CSS 选择器（默认）
      return document.querySelector(selector);
    };
    
    // 解析所有匹配元素
    (window as any).__MCP__.resolveAll = function(selector: string, strategy?: string): Element[] {
      if (!selector) return [];
      
      if (strategy === 'xpath') {
        const snapshot = document.evaluate(selector, document, null,
          XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        const results: Element[] = [];
        for (let i = 0; i < snapshot.snapshotLength; i++) {
          results.push(snapshot.snapshotItem(i) as Element);
        }
        return results;
      }
      
      return Array.from(document.querySelectorAll(selector));
    };
    
    // 计数匹配元素
    (window as any).__MCP__.countAll = function(selector: string, strategy?: string): number {
      return (window as any).__MCP__.resolveAll(selector, strategy).length;
    };
    
    console.log('[MCP] Helper functions injected');
  };
  
  injectMcpHelpers();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectMcpHelpers);
  }
}
```

---

## 验证配置

完成以上配置后，重新启动应用并验证：

```bash
# 1. 重启 Tauri 应用
cargo tauri dev

# 2. 等待启动完成后，连接 Session
tauri-mcp driver-session start --port 9223

# 3. 验证辅助函数是否注入
tauri-mcp webview-execute-js --script "
  (() => ({
    hasResolveRef: typeof window.__MCP__?.resolveRef === 'function',
    hasResolveAll: typeof window.__MCP__?.resolveAll === 'function',
    hasCountAll: typeof window.__MCP__?.countAll === 'function'
  }))()
"

# 应该返回：
# {"hasResolveRef":true,"hasResolveAll":true,"hasCountAll":true}
```

---

## 配置检查清单

- [ ] `Cargo.toml` 添加了 `tauri-plugin-mcp-bridge`
- [ ] `lib.rs` 调用了 `.plugin(tauri_plugin_mcp_bridge::init())`
- [ ] `tauri.conf.json` 设置了 `"withGlobalTauri": true`
- [ ] `capabilities/default.json` 添加了 `"mcp-bridge:default"`
- [ ] 前端入口文件注入了辅助函数
- [ ] 重新编译并启动应用
- [ ] 验证辅助函数已注入

---

## 常见问题

**Q: 为什么需要 `withGlobalTauri: true`？**  
A: MCP Bridge 需要通过 `window.__TAURI__` 对象与 WebView 通信。这个设置确保 Tauri API 暴露在全局作用域。

**Q: 辅助函数为什么要放在前端代码里？**  
A: 这些是元素选择器的辅助函数，需要在 WebView 上下文中执行。虽然 MCP Bridge 会尝试注入，但在某些场景（如复杂前端框架）可能失败，手动注入最可靠。

**Q: 生产环境需要这些配置吗？**  
A: 不需要。MCP Bridge 只在 debug 构建中运行（由 `#[cfg(debug_assertions)]` 控制），生产环境不会加载。
