---
name: public-ai-resource-research
description: Investigate public AI access resources across forums, communities, directories, search engines, and the open web. Use when Codex needs to search one platform such as Linux.do or a broader web scope for public welfare stations, relay sites, signup flows, model-support claims, availability reports, public base URLs, or status signals, and return a reusable evidence ledger for later validation. Do not use this skill to harvest or republish unauthorized secrets; record only public URLs and redacted or user-authorized secret references.
---

# 公开 AI 资源调研

用这个 skill 把类似“查一下 Linux.do 里的公益站”这种临时需求，变成可重复执行的调研流程与结构化产物。

这个 skill 负责“发现与整理证据”，不负责接口探测。需要做健康检查或模型可用性验证时，再把结果交给后续 probe 流程。

## 快速开始

1. 如果用户希望有持续维护的产物，先初始化一个 case 目录：

```bash
python scripts/init_case.py /absolute/path/to/case \
  --scope "linux.do 公益站与中转站检索" \
  --platform linux.do
```

2. 先写查询矩阵，再开始搜索。
3. 按层搜索：站内信号、搜索引擎索引、导航/监测页、维护帖反查、全网扩展。
4. 先记 ledger，再写总结。
5. 最终按“实体”归纳，不按搜索顺序归纳。

需要构造查询式时，读取 [references/search-recipes.md](references/search-recipes.md)。

需要理解结构化字段时，读取 [references/ledger-schema.md](references/ledger-schema.md)。

如果用户想长期维护目录或网站，就把 ledger 当成单一数据源，让人类可读页面从结构化数据生成，而不是反过来从 Markdown 拼装。

## 工作流

### 1. 先锁定范围与敏感边界

先明确：

- 搜索范围：单站、多社区，还是全网
- 目标对象：公益站、中转站、注册入口、导航页、共享凭据帖、状态页
- 时间范围：最新、历史扫街，还是两者都要
- 交付形式：短答复、Markdown 文档，还是可持续维护的 ledger

从一开始就区分三类证据：

- `公开基础设施`：站点 URL、文档 URL、状态页、导航页、话题页
- `社区声明`：支持哪些模型、是否限流、是否要 OAuth / CDK / 邀请码、是否维护中
- `敏感接入材料`：API key、Auth Token、Cookie、邀请码、私有 relay 凭据

不要收集或转存第三方 secret。这里只记录：

- 非敏感的公开 base URL
- 是否观察到凭据
- 凭据出现在哪里
- 用户后续是否提供了授权的 secret 引用

### 2. 搜索前先写查询矩阵

不要边搜边临时想关键词。先按族构造查询：

- 实体查询：站名、别名、昵称、运营者
- 任务查询：`公益站`、`中转站`、`API`、`Claude Code`、`Codex`、`OpenAI`、`DeepSeek`、`Gemini`
- 证据查询：`开放资源`、`key`、`Auth Token`、`Base URL`、`兑换码`、`OAuth`、`签到`
- 维护查询：`失效`、`维护`、`迁移`、`公告`、`关闭`、`可用模型`
- 导航查询：`导航`、`汇总`、`监测`、`check`、`hub`

对论坛类平台，既搜关键词，也搜稳定标识符，比如 topic id、站点名、引用标题。很多旧帖只能靠后续回复、转引帖或镜像反查出来。

### 3. 按层搜索

除非平台限制很特殊，否则按这个顺序：

1. 站内搜索、标签页、列表页、JSON 接口
2. 限定站点的搜索引擎查询
3. 已知导航站、监测页、汇总页
4. 从较新的维护帖、故障帖反查更早的原贴
5. 向全网扩展到官网、文档、状态页、GitHub 仓库、社区镜像

Linux.do 这次调研的经验是：

- 站内接口被 Cloudflare 挡住时，搜索引擎反而更容易把 topic id 暴露出来。
- 导航页和监测帖比逐个站名硬搜更高效。
- 很多原贴难找，但维护公告和故障帖反而更容易搜到。
- 先写长文、后补证据效率很低；ledger-first 会明显更稳。

### 4. 立刻做实体归一化

每个服务或站点只保留一条实体主记录，不要让每个帖子都变成一个新对象。

至少尽早归一化这些字段：

- 标准名
- 别名
- 对象类型
- 所属平台范围
- 鉴权方式：公开、OAuth、邀请码、CDK、注册、按人分 key、未知
- 是否有公开 base URL
- 声称支持的模型
- 当前状态：正常、退化、仅邀请、迁移、可能失效、已失效、未知

如果某条信息只出现在社区讨论里，就把它标成“声明”，直到被官方来源或多源交叉验证支撑。

### 5. 把 source、entity、access、status 分开记

不要把所有信息塞进一篇 Markdown。

至少拆成这些层：

- 查询矩阵：搜了什么、为什么搜
- 来源 ledger：引用过的帖子、页面、文档
- 实体 ledger：每个站点 / relay 一条
- 接入观察：哪里出现过公开 base URL 或凭据线索
- 状态检查：后续 probe 或验证的候选目标

这样做的好处是：

- 容易去重
- 容易从结论反查来源
- 容易把干净的目标交给后续探测 skill
- 更新状态时不用重写整篇文档

### 6. 只有在 ledger 可信之后再写总结

发现阶段结束后，按这些维度总结：

- 导航与聚合基础设施
- 主要实体
- 提到共享接入材料的帖子
- 当前未知点与待验证目标

明确标出哪些是直接观察，哪些是推断。

### 7. 只有在用户授权时才交给 probe

如果某一行已经有公开 base URL，而用户后续提供了授权凭据引用：

- discovery ledger 本体不改，只补 `authorized_secret_ref`
- 把该目标交给 `$relay-endpoint-probe`
- 把 probe 结果回写到目录里，更新状态或 `observed_models`

不要把公开帖子里抓到的第三方 key 直接交给 probe。

## 输出规则

默认输出是 Markdown 报告加结构化 ledger。

始终包含：

- 与时间有关的信息要写具体日期
- 引用公开页面时写绝对 URL
- 给出简短的证据质量说明
- 如果平台阻止了直接验证，要明确写出不确定性

推荐使用这些状态标签：

- `alive`
- `degraded`
- `invite-only`
- `login-only`
- `migrated`
- `probably-dead`
- `dead`
- `unknown`

推荐使用这些证据标签：

- `official`
- `community-primary`
- `community-secondary`
- `mirror`
- `inference`

## 安全边界

这个 skill 可以记录公开 URL、公开 base URL 和公开模型声明。

这个 skill 不能自动抓取、提取、传播第三方 API key、Auth Token、Cookie 或其他 live secret。

如果用户后续提供了自己授权使用的凭据，默认只记录用户指定的 `authorized_secret_ref` 或其他站外引用，而不是把敏感值直接写进目录。

## 资源

- `scripts/init_case.py`：初始化 case 目录、ledger 和 notes
- `references/search-recipes.md`：查询族、搜索顺序和全网扩展套路
- `references/ledger-schema.md`：结构化字段定义
