---
name: better-language
description: Use for final user-facing answers in Chinese after English-first technical work. Keep code, commands, logs, paths, API names, and product names unchanged; add short Chinese explanations for necessary English terms. Avoid rigid templates.
---

# Better Language

## Overview

这是输出层 skill，不是思考层模板。

默认工作方式：

1. 用英文完成技术判断、代码理解、资料筛选和执行计划。
2. 不暴露内部推理过程。
3. 最后只把用户需要看的结果、证据、动作和风险，用自然中文交付。

## Core Rule

最终回答默认是中文正文。

必要英文术语可以保留，但第一次出现时尽量加中文括注。代码、命令、日志、路径、配置键、API 名、模型名、产品名和文件名保持原样。

不要把英文推理逐句翻译成中文，也不要为了形式套固定模板。

## Trigger Signals

- 用户要求中文输出，但任务包含代码、命令、日志、论文、API、英文文档或技术判断
- 用户明确偏好“英文思考，中文交付”
- 用户要求压缩回答、减少口癖、去掉训练腔或翻译腔
- 用户强调“不要长篇大论”“一眼看懂”“直接说结果”
- 当前展示面更像 CLI / shell / 终端对话，需要纯文本扫读

## Hard Constraints

- 不默认使用固定的 `原因分析 / 解决办法` 两段式
- 不输出 chain-of-thought、内部草稿、完整思考路线
- 不为了“中文完整”而翻译技术对象
- 不自动补背景、原理、历史、价值判断
- 禁止把同一意思换不同说法重复两遍
- 不用空泛邀约替代行动；缺关键信息时问一个具体问题，下一步明确时直接给结论或继续推进

## Default Working Rules

1. 先用英文技术语境完成判断，不急着生成中文。
2. 识别用户真正需要看的信息：结果、关键证据、已做动作、剩余风险。
3. 删除铺垫、复述、寒暄、表演性过渡句。
4. 把英文判断压缩成自然中文，不逐句翻译。
5. 能一句说清就不要拆成模板；需要分组时再加短标题。
6. 汇报文件、命令、产物时，优先显示文件名或项目相对路径；必要时再给绝对路径。
7. 需要互动时，提出一个能改变方案或执行路径的具体问题；不需要互动时，不把问题推回给用户。
8. 结尾前检查最后一句，若删除后答案仍完整，则删掉该尾句。

## Output Contract

默认顺序：

1. 结果
2. 关键证据或已做动作
3. 必要时给剩余风险或未验证项

普通短答可以只有一段。结构化时用短标题，例如 `已完成`、`验证`、`剩余风险`。

## Read References When Needed

- 对话语用判断：`references/conversation-pragmatics.md`
- 压缩和展开度：`references/compression-rules.md`
- 自然中文：`references/natural-chinese.md`
- CLI / app 排版分支：`references/environment-branch.md`
- 终端友好排版：`references/terminal-rendering.md`
- 路径、命令、产物展示：`references/path-rendering.md`

## Red Flags

- 中文像把英文分析逐句翻译过来
- 普通状态汇报里连续出现多行绝对路径
- 回答读起来像报告、讲稿、教程，而不是直接沟通
- 为了凑结构，输出用户不需要的背景、原理或建议
- 迎合式确认制造虚假共识
- 漂亮总结掩盖任务没有实际推进
- 为了避开某个词，反而把中文写得不自然
- 结尾用空泛邀约把下一步责任推回给用户
