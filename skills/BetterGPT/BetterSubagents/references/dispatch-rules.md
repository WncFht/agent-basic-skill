# Dispatch Rules

## 1. 何时值得派发

只有满足以下条件之一时，才优先考虑派发：

- 子任务独立，且不会阻塞主代理当前下一步
- 可以并行推进多个互不依赖的问题
- 需要专用能力，明显比通用 agent 更合适

以下情况优先主代理本地处理：

- 当前下一步就依赖该结果
- 边界不清，派发成本大于收益
- 写集明显冲突
- 只是一个很小的直接操作

## 2. 派给谁

- 代码定位 / 路径梳理 → `code-mapper`
- 搜索入口 / 预筛命中 → `search-specialist`
- 纯证据调查 → `explorer`
- 风险审查 → `reviewer`
- 文档核验 → `docs-researcher`
- 前端实现 → `frontend-developer`
- 浏览器复现 → `browser-debugger`
- 低风险重构 → `refactoring-specialist`
- 通用实现兜底 → `worker`

### 2.1 优先级链

- 调用链、主路径、ownership boundary  
  → `code-mapper` > `explorer`
- 官方文档、默认值、版本差异、API 语义  
  → `docs-researcher` > `search-specialist`
- 前端交互异常复现、浏览器证据  
  → `browser-debugger` > `frontend-developer`
- 前端明确实现、组件修复、状态变更  
  → `frontend-developer` > `worker`
- 低风险结构重构、职责拆分  
  → `refactoring-specialist` > `worker`

### 2.2 排他规则

- 文档核验任务，不先派 `search-specialist`
- 调用链梳理任务，不先派 `explorer`
- 浏览器复现任务，不先派 `frontend-developer`
- 前端明确实现任务，不先派 `browser-debugger`
- 结构重构任务，不先派 `worker`

## 3. 派发内容最少要包含

- 任务类型
- 子任务目标
- 修改边界或只读边界
- 预期输出
- 是否需要验证
- 需要使用的技能或工具约束
- 需要优先参考的 spec / workflow / 目录路径（若存在）
- 退出条件

### 3.0 建议派发模板

```text
任务类型：
目标：
边界：
预期输出：
验证要求：
skill / spec / MCP 约束：
退出条件：
```

### 3.1 skill 绑定规则

- 前端页面实现、视觉成品化、UI 行为修复  
  → `BetterFrontend`
- 前后端边界、服务拆分、低风险结构重构  
  → `BetterVibe`
- Trellis workflow、spec、task、record-session、hooks  
  → `BetterTrellis`

如果一个子任务同时命中多个领域，派发说明里必须一起写明，不要只写一个泛化目标。

### 3.2 MCP 绑定规则

- 仓库代码定位、调用链、实现搜索  
  → `ace-tool`
- 外部联网搜索、资料预筛  
  → `grok-search`
- 第三方库 / SDK / API 文档核验  
  → `Context7`
- 已知页面原文核对、逐页阅读、精确引用  
  → 系统 `web`

不要把 MCP 分工只留在主代理脑内，派发说明里要写给子代理。

补充：

- `grok-search` 默认用于“先搜到入口、先拿到多来源摘要”
- 如果任务已经给出明确页面、要求精确出处、或需要逐页核对原文  
  → 应切到系统 `web`，不要只停留在搜索聚合结果

## 4. 等待与接管

- 对子代理结果的等待，使用 `wait_agent`
- 只有主线程下一步真的被阻塞时，才 `wait_agent`
- 如果主线程还有可做的非重叠工作，不要一派发就等待
- 默认最多等待 3 轮，每轮 120 秒
- 第 1 轮 `wait_agent` 超时：先检查是否仍在推进
- 第 2 轮等待仍无进展：补充边界或目标，必要时 `send_input`
- 第 3 轮等待后仍卡住：中断 / 关闭并由主代理接管
- 如果卡点是权限、环境、依赖、共享写集冲突  
  → 不继续空等，直接回到主线程处理阻塞

### 4.1 纠偏与催促

- `send_input` 只用于补边界、纠偏、打断改道
- 不用 `send_input` 做“你现在快点”“还没好吗”式催促
- 没有新增信息时，不要频繁打扰正在正常工作的子代理

### 4.2 完成后关闭

- 子代理一旦完成且结果已被主代理吸收  
  → 立即 `close_agent`
- 不因为“也许稍后还会问一句”而默认保留
- 已完成 agent 若无明确连续追问计划，应及时关闭

### 4.3 复用条件

只有以下情况可复用原 agent：

- 后续问题与上一任务高度连续
- 任务边界、skill 绑定、MCP 分工没有变化
- 复用原上下文明显优于新开 agent

以下情况优先新开 agent：

- 从调查转实现
- 从复现转修复
- 从文档核验转代码改动
- 任务目标或边界已变化

## 5. 主代理介入条件

- 子代理连续超时
- 输出明显偏题
- 写集冲突
- 外部依赖阻塞
- 多个结果冲突
- 子代理明确报告“更适合其他专用 agent”
- 子代理已完成但仍长期挂在后台

## 6. MCP 使用原则

如果子任务需要工具，默认按工作区分工：

- 外部搜索 → `grok-search`
- 代码搜索 → `ace-tool`
- 第三方文档 → `Context7`
