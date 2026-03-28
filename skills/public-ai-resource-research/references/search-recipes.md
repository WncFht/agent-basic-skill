# 搜索配方

当任务重点是“发现”，而不是“探测”时，读取这份参考。

## 1. 单社区搜索

先用限定站点的查询：

- `site:<domain> 公益站`
- `site:<domain> 中转站`
- `site:<domain> API key`
- `site:<domain> Base URL`
- `site:<domain> Auth Token`
- `site:<domain> 明文 key`
- `site:<domain> 泄露 key`
- `site:<domain> Claude Code`
- `site:<domain> Codex`
- `site:<domain> DeepSeek`

再扩展维护类语言：

- `site:<domain> 维护`
- `site:<domain> 失效`
- `site:<domain> 更新`
- `site:<domain> 公告`
- `site:<domain> 迁移`

再扩展基础设施类语言：

- `site:<domain> 导航`
- `site:<domain> 汇总`
- `site:<domain> 监测`
- `site:<domain> check`
- `site:<domain> hub`

## 2. 反向引用回溯

如果原贴很难找到：

1. 先找更新帖、维护帖、故障帖。
2. 抽取稳定标识符：topic id、站名、运营者、引用标题。
3. 用这些标识符反搜。
4. 特别盯住“原贴”“主贴”“更新贴”“维护公告”“迁移公告”这类词。

这就是 Linux.do 这次调研里最值得固化的方法。

## 3. 别名扩展

至少维护三类别名：

- 官方名
- 社区简称 / 昵称
- 运营者 / 团队名

还要按模型词汇扩展：

- `OpenAI`
- `Anthropic`
- `Claude`
- `Claude Code`
- `Codex`
- `DeepSeek`
- `Gemini`
- `GLM`
- `Kimi`

## 4. 向全网扩展

从社区发现之后，按这个顺序向外搜：

1. 官网或文档
2. 官方状态页
3. GitHub 仓库或文档仓
4. 公开监测页或仪表盘
5. 社区镜像与复盘帖

社区帖子可以当线索，但以下几类信息优先用官方来源确认：

- 支持哪些模型
- 鉴权方式
- 价格与额度
- 维护状态
- 迁移公告

## 5. 证据记录

在搜索时就记录证据等级：

- `official`：运营方控制的页面或仓库
- `community-primary`：原始帖子或运营者回复
- `community-secondary`：后续讨论、复盘、转引
- `mirror`：镜像或转载
- `inference`：由若干弱信号推出来的结论

## 6. 敏感观察

对于公开接入材料，只记录安全元数据：

- 是否观察到凭据
- 凭据出现在哪里
- base URL 是否公开
- 附近声称支持哪些模型
- 是否适合后续验证
- 一个不含 secret 的定位符，例如 topic id、帖子 URL、截图位置或引用标题

不要把第三方 live 凭据原文贴进 ledger。
