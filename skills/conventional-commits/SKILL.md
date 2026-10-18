---
name: conventional-commits
description: 统一 Git 提交信息的 Conventional Commits 规范，帮助编写简洁、可审查且可自动化处理的提交。
---

# Conventional Commits 提交规范

提交信息整体使用英文，并遵循 Conventional Commits 格式：

```text
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

## 提交类型

| 类型     | 用途                                 |
| -------- | ------------------------------------ |
| feat     | 新增功能。                           |
| fix      | 修复缺陷。                           |
| docs     | 仅修改文档。                         |
| refactor | 既不新增功能也不修复缺陷的代码变更。 |
| perf     | 性能优化。                           |
| test     | 新增或更新测试。                     |
| build    | 构建系统或依赖变更。                 |
| ci       | CI 配置变更。                        |
| chore    | 仓库维护。                           |
| revert   | 回退之前的提交。                     |

## 编写规则

1. 使用祈使语气。
2. 描述保持简洁，末尾不加句号。
3. 使用稳定的 scope，例如包、子系统或业务领域。
4. 在可行的情况下，将标题控制在 72 个字符以内。
5. 对于不明显的变更，在正文说明变更原因。
6. 破坏性变更使用 `!`，并添加 `BREAKING CHANGE:` footer。
7. 破坏性变更必须附上迁移说明。
8. 能提供有用上下文时，使用 `Refs: #123` 等 trailer。
9. 一个提交只聚焦一个逻辑变更。
10. 工作过程中自主创建提交。
