# Environment Branch

## Core Goal

先判断当前回答落在哪种展示面，再决定排版方式。

## Default Decision

- 普通 app 聊天界面  
  → 用 `BetterLanguage` 默认轻量排版
- CLI / terminal / shell / 终端对话  
  → 用 `BetterLanguage` 内容规则 + 终端友好排版

## Strong Signals For CLI

- 当前上下文里明确出现 `cwd`、`shell`、命令输出、终端日志
- 用户明确说“终端里看”“CLI 输出”“命令行里阅读”
- 当前任务主要围绕命令、路径、报错、脚本、代码审查输出展开
- 当前界面明显更依赖纯文本阅读，而不是富文本卡片或图像

## Strong Signals For App

- 当前界面支持富文本、图片、按钮、directive 或更强的图形化能力
- 用户正在进行普通聊天，而不是终端导向的任务对话
- 当前任务重点是解释、规划、产品讨论，而不是终端内操作

## Fallback Rule

如果不能明确判断，就默认走普通 `BetterLanguage`，不要误加过重的终端排版。

## Important Boundary

环境分支只改变排版，不改变核心内容规则：

- 仍然保留两大段
- 仍然压缩展开度
- 仍然禁用口癖和翻译腔
