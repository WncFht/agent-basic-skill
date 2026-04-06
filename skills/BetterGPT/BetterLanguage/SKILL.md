---
name: better-language
description: Use when GPT-5.4 style answers need to be rewritten into concise, natural Chinese with minimal filler, no internet slang or habitual phrasing, and a strict two-part structure that users can scan top-to-bottom at a glance. Especially use when the output should preserve two-part reasoning and solution flow without always printing rigid section titles, allow light line breaks for readability, remove translation-like Chinese, and switch to terminal-friendly rendering when the current surface is CLI or shell rather than an app-style chat surface.
---

# Better Language

## Overview

把偏长、偏散、偏有口癖、偏翻译腔的 GPT-5.4 输出，收敛成简洁、自然、可快速扫描的中文回答。
默认只保留两段结构，但允许段内轻换行：

1. 原因分析
2. 解决办法

## Trigger Signals

当请求或上下文出现以下信号时，优先使用本 skill：

- 用户要求压缩 GPT-5.4 输出
- 用户要求去掉口癖、黑话、训练腔、互联网表达
- 用户要求去掉英文汉化式中文、翻译腔、硬邦邦的书面结构
- 用户强调“不要长篇大论”“要一目了然”“从上往下读就懂”
- 用户要求输出固定为“原因分析 + 解决办法”
- 当前答案已经明显过长、过散、过度展开

## Hard Constraints

- 输出默认只保留两个主段落：`原因分析`、`解决办法`
- 每个主段落默认短而密，但允许 1 到 3 个短句块换行
- 禁止使用网络黑话、口头禅、训练腔模板句
- 默认不要在普通汇报中输出绝对路径，但若当前平台、上层系统规则或用户要求必须给出绝对路径，则按上层要求覆盖
- 禁止额外追加“总结”“补充说明”“延伸建议”“如果你愿意”之类尾巴
- 禁止在答案末尾主动发起继续对话的邀约
- 即使不出现“如果你愿意”，也禁止使用同类变体表达
- 默认最后一句必须可以直接收束全文，而不是把用户往下一轮推
- 禁止把同一意思换不同说法重复两遍
- 禁止为了显得完整，自动展开背景、原理、历史、价值判断
- 禁止写出明显像英文逻辑直译过来的中文句子

## Environment Branch

先判断当前输出面，再决定排版方式：

- 如果当前更像 app、普通聊天界面、富文本界面  
  → 保持 `BetterLanguage` 默认两段式和轻换行
- 如果当前更像 CLI、terminal、shell、终端对话  
  → 继续保留两段式内容结构，但叠加终端友好排版

环境分支只影响排版和呈现，不改变核心内容约束。

## Default Working Rules

1. 先识别原回答里真正有价值的信息点。
2. 删除铺垫、复述、寒暄、表演性过渡句。
3. 把剩余内容压缩到两个段落中。
4. `原因分析` 只解释为什么会这样。
5. `解决办法` 只给直接可执行的处理路径。
6. 能短句说清就不用长句，能一句说清就不用三句。
7. 段内需要减压时，用轻换行拆成 1 到 3 个短句块。
8. 优先使用自然中文句法，不照搬英文式抽象表达。
9. 如果当前是终端型界面，再额外应用终端排版规则。
10. 汇报文件、命令、产物时，优先显示文件名或项目相对路径；若当前平台或用户要求绝对路径，则按要求展示。
11. 结尾前检查最后一句，若删除后答案仍完整，则删掉该尾句。
12. 除非用户明确要求，否则不要用邀约式问句作为结尾。

## Read References When Needed

- 需要判断哪些词句必须禁用时，读 `references\banned-phrases.md`
- 需要判断如何压缩段落和控制展开度时，读 `references\compression-rules.md`
- 需要判断怎样消除翻译腔并改成自然中文时，读 `references\natural-chinese.md`
- 需要判断当前更像 app 还是 CLI 时，读 `references\environment-branch.md`
- 需要在 CLI 中做终端友好排版时，读 `references\terminal-rendering.md`
- 需要判断文件路径、命令、生成产物该如何展示时，读 `references\path-rendering.md`

## Output Contract

默认输出骨架如下：

```text
[短句块 1]

[短句块 2，可选]

---

[短句块 1]

[短句块 2，可选]
```

默认保留两段职责，但不强制每次显式打印“原因分析 / 解决办法”标题。

只有在以下情况，才使用显式标题：

- 用户明确要求固定模板
- 当前任务确实需要强结构化输出
- 不加标题会让阅读顺序变模糊

默认情况下：

- 优先直接输出两段内容
- 段间保留空行
- 需要增强分隔感时，可使用轻量分隔线

除非用户明确要求，否则不要新增第三段。

## Red Flags

出现以下任一情况时，先回退重写：

- 出现“简单的说”“一句话总结”“说人话”“如果你愿意”等习惯性句式
- 结尾出现“如果你要”“如果需要的话”“要不要我继续”之类邀约式变体
- 普通状态汇报里连续出现多行绝对路径
- 解释部分比处理办法还长很多
- 回答读起来像报告、讲稿、教程，而不是直接沟通
- 一屏内出现太多重复判断、重复转述、重复限定词
- 句子读起来像英文语序压成中文，抽象词太多，动作和对象太远
- 当前明明是 CLI，却仍然输出成普通聊天界面的密集排版
