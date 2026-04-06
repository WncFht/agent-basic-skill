---
name: better-frontend
description: Use when generating, revising, polishing, or reviewing frontend UI, landing pages, dashboards, app screens, marketing pages, or other presentation-layer output that should look like a production-ready product instead of a demo, draft, wireframe, showcase, or developer-facing mockup. Especially use when the request mentions removing AI-like UI, avoiding demo feel, preventing TODO or note text, hiding reasoning or design commentary from users, eliminating placeholder explanations, or making the final interface feel shippable, real, and user-facing.
---

# Better Frontend

## Overview

把所有前端展示层任务默认当作正式可交付成品处理。
优先保证用户可见结果可直接落地，而不是像原型、草稿、演示稿或开发中间态。

## Trigger Signals

当请求或上下文出现以下信号时，应优先使用本 skill：

- 用户要求做前端页面、落地页、仪表盘、控制台、工作台、营销页、应用界面
- 用户强调“像正式产品”“能上线”“不要 demo 感”“不要 AI 味”
- 用户要求删除用户可见界面中的开发者备注、思路说明、设计评论、占位解释
- 用户提到“不准把 TODO / NOTE / mock / placeholder / reasoning 放到页面里”
- 用户要求“润色 UI”“收敛视觉输出”“把页面改得更像真实产品”
- 当前方案明显更像原型、概念稿、样板页、作品集展示，而不是正式成品

## When Not to Use

- 用户明确要求 wireframe、低保真草图、教学示例页、组件演示页
- 任务只是在写技术文档、设计说明、评审备注，而不是在生成用户可见前端
- 任务只涉及后端接口、数据库、脚本或 CLI，不涉及展示层输出

## Hard Constraints

- 禁止把面向开发者的备注、思维过程、设计评论、实现说明、占位解释输出到用户可见界面。
- 禁止把“材质感、光影、动效、视觉工艺”的解说型文案写进用户可见副标题、说明文案、卡片描述。
- 默认按正式产品界面开发，不按 demo、wireframe、概念稿、展示稿思路产出。
- 优先交付真实用户可理解、可操作、可上线的前端结果。
- 非用户显式要求时，不向界面中加入“开发中”“示例数据”“后续接接口”“这里可扩展”等说明性文本。
- 不与当前项目内的 `.trellis/spec/frontend/*` 长期维持两套平行前端规范。

## Default Working Rules

1. 先判断哪些内容属于用户可见展示层，哪些内容只应留在代码、注释或对话中。
2. 对展示层文案做一次泄漏检查，删掉所有开发者视角文本。
3. 对页面结构做一次产品化检查，确认它像正式成品，而不是演示模板。
4. 优先收敛界面信息密度、视觉层级、组件用途和文案意图，避免为了“解释设计”而污染界面。
5. 副标题、说明文案、卡片描述默认必须服务用户任务：解释状态、结果、风险、收益、下一步动作；如果主要是在描述界面怎么好看、材质怎么真实、动效怎么细腻，就不应进入展示层。
6. 如果页面类型是功能页、工具页、数据页、控制台、工作台，默认禁止把营销页式氛围描写、设计旁白、展示稿话术带入副标题。
5. 如果当前项目存在 `.trellis/spec/frontend/`，前端规范优先参考该目录；本 skill 自带 references 只做补充，不单独形成第二套平行规范。

## Read References When Needed

- 需要判断哪些内容绝不能进入展示层时，读 `references/banned-content.md`
- 需要判断默认成品化标准时，读 `references/production-defaults.md`
- 需要判断前端视觉输出约束时，读 `references/visual-rules.md`
- 需要做 dashboard、admin、workbench 等后台页面时，读 `references/page-rules-dashboard.md`
- 需要做 landing page、营销页、品牌展示页时，读 `references/page-rules-landing.md`
- 需要交付前做最终自检时，读 `references/pre-delivery-checklist.md`

## Red Flags

出现以下任一情况时，先停下并回退：

- 页面上出现 TODO、NOTE、placeholder explanation、mock 提示、设计备注
- 用户可见文案在解释“这个模块是干什么的给开发者看”
- 用户可见副标题或描述文案在解释玻璃、高光、折射、渐变、漂浮、镜面、雾面、霓虹、层叠、虚化等视觉工艺
- 页面文案读起来像作品集、设计稿旁白、展示稿解说，而不是产品界面语言
- 页面更像模板站、演示稿、AI 样例，而不像真实产品
- 为了说明思路，把实现过程、评审说明或设计讨论直接写进 UI
