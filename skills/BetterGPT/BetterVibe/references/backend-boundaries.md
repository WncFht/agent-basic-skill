# Backend Boundaries

## Core Goal

让后端结构保持分层清楚、职责单一、副作用可控。

## Layering Rules

- 路由层 / controller / handler 负责接入、校验、调用，不负责堆业务
- service 层负责业务编排，不负责承载所有东西
- repository / DAO / persistence 层负责数据访问，不负责业务判断

## Service Discipline

- 一个 service 只负责一个业务域
- 跨域流程通过明确编排完成，不要把所有逻辑塞进同一个 service
- 不要把 service 写成“万能入口”

## Data Boundary Rules

- API DTO、领域对象、数据库模型不要混用
- 不要让数据库表结构直接决定接口返回结构
- 不要把“库里怎么存”直接暴露成“前端怎么拿”

## Side Effects

- 缓存、消息、第三方调用、落库、副作用更新要有明确边界
- 不要让核心业务函数顺手做一堆隐藏副作用
- 复杂副作用链要能拆解和测试

## Anti-Patterns

- 巨型 controller
- 巨型 service
- 巨型 handler
- 同一个方法里同时做校验、业务、持久化、返回组装
- 看起来只有一层 service，实际上里面塞了所有系统复杂度
