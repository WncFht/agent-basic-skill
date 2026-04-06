# Agent Registry

当前工作区本地 `agents/` 目录中的主要 subagent：

## 调查型

- `explorer`：通用只读调查兜底
- `code-mapper`：调用链、执行路径、ownership boundary
- `search-specialist`：高信号搜索与下一步入口发现

## 审查 / 核验型

- `reviewer`：风险审查、回归、缺测试
- `docs-researcher`：官方文档、版本、API 语义核验

## 实现型

- `worker`：通用实现兜底
- `frontend-developer`：前端实现与 UI 修复
- `refactoring-specialist`：低风险结构重构

## 浏览器取证型

- `browser-debugger`：浏览器复现、UI 证据收集、客户端调试

## 优先原则

1. 有专用 agent 时，优先专用 agent
2. 没有专用 agent 时，再退回 `explorer` / `worker`
3. 读型任务优先只读 agent
4. 写型任务优先实现型 agent

## 优先级链

- 调用链 / ownership / 主路径  
  → `code-mapper` > `explorer`
- 官方文档 / 默认值 / API 语义  
  → `docs-researcher` > `search-specialist`
- 浏览器复现 / 前端证据  
  → `browser-debugger` > `frontend-developer`
- 前端明确实现  
  → `frontend-developer` > `worker`
- 结构重构 / 职责拆分  
  → `refactoring-specialist` > `worker`

## 使用边界

- `explorer`：只读兜底，不负责完整调用链梳理、文档语义核验、浏览器复现和代码实施
- `worker`：实现兜底，不负责替代前端专项和结构重构专项
- `search-specialist`：负责找入口，不负责文档事实裁定和完整调用链图谱
- `browser-debugger`：负责复现和证据，不负责默认接管前端实现
