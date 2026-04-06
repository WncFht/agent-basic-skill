---
name: better-vibe
description: Use when designing, reviewing, or implementing full-stack application structure and engineering boundaries. Especially use when frontend pages are becoming overloaded, presentation code is mixing with backend concerns, backend services are growing into large coupled modules, or the system needs clearer separation between UI, business logic, persistence, and cross-layer responsibilities.
---

# Better Vibe

## Overview

这是一个全栈工程护栏 skill。

它不负责讲具体框架 API，重点是约束：

- 前端页面职责
- 后端分层边界
- 前后端耦合方式
- 模块拆分与可维护性

## Trigger Signals

当请求或上下文出现以下信号时，优先使用本 skill：

- 单个前端页面越来越重，开始堆逻辑、堆状态、堆展示
- 展示层开始混入后端能力、业务编排、复杂数据处理
- 后端 controller / service / handler 变得过大、过杂、过耦合
- 前后端边界混乱，职责分配不清
- 项目虽然能跑，但维护成本明显升高
- 用户明确要求从全栈工程角度约束架构和职责

## Core Rule

先判断问题属于哪一层：

1. 前端页面职责问题
2. 后端分层问题
3. 前后端边界问题

再按需读取对应 reference，不要一次性展开全部细节。

## Default Working Rules

1. 先识别当前问题的主要耦合点。
2. 判断问题主要落在前端、后端，还是边界层。
3. 优先做职责拆分，而不是继续往现有大文件或大模块里堆代码。
4. 优先保证层与层之间职责清楚，而不是局部代码“暂时能跑”。
5. 默认追求可维护、可替换、可测试的结构。
6. 如果当前项目存在 `.trellis/spec/backend/` 或 `.trellis/spec/guides/`，边界与分层规范优先参考这些项目内文档；本 skill 自带 references 只做补充。

## Read References When Needed

- 需要判断前端页面职责和展示层边界时，读 `references\frontend-boundaries.md`
- 需要判断后端分层、服务边界和副作用隔离时，读 `references\backend-boundaries.md`
- 需要判断前后端如何解耦、如何分配职责时，读 `references\fullstack-boundaries.md`

## Hard Constraints

- 不把前端页面当成业务编排中心
- 不把后端 service 当成万能垃圾桶
- 不把数据库结构直接暴露成前端接口结构
- 不让前后端为了省事互相吞掉对方职责
- 不因为“当前能跑”就接受明显会继续膨胀的结构
- 不与当前项目内的 `.trellis/spec/backend/*`、`.trellis/spec/guides/*` 长期维持两套平行边界规范

## Red Flags

- 单个页面文件越来越长，而且同时在做展示、状态、数据、流程控制
- controller / handler 里直接塞大量业务判断和数据处理
- service 里同时做权限、事务、缓存、第三方调用、返回组装
- 前端为了拿到页面数据，不得不依赖后端返回高度展示化结构
- 改一个需求时，前后端两边都要跟着大改
