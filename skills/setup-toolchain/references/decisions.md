# 分叉决策

合理的仓库之间会不一样的那些选择。每项先给推荐答案；这里的推理是给用户反驳或仓库形态迫使走另一支时用的。

## ts/js formatter——三选一

|            | prettier + eslint + tsc                                             | biome                                                  | oxfmt + oxlint                                 |
| ---------- | ------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------- |
| 是什么     | 生态默认，三个工具                                                  | 一个 rust 二进制：format + lint + imports + json + css | 最新的 rust 组合，最快                         |
| 风格还原度 | prettier 本体                                                       | 输出 ~97% 兼容 prettier                                | oxc 声称 ~100% prettier 一致，快 ~30x          |
| lint 深度  | 生态里所有插件                                                      | 内置规则不错，但插件生态还没对齐                       | 规则是子集——适合当快速门，不是完整 eslint 替代 |
| 什么时候选 | 应用型仓库、要插件（tailwind-sort、svelte、astro、vue）、团队熟悉度 | 新仓库、求一个工具搞定、少依赖、json/css 也覆盖        | 大仓库、hook 延迟是痛点、lint 需求不高         |

**推荐**：prettier + eslint + tsc——base 层已经给 md/yaml 用了它，js/ts 搭同一个 devDep、同一个 `--stdin-filepath {}` 机制。新仓库且看重单工具简洁就选 biome；hook 延迟是主要抱怨就选 oxfmt+oxlint。三种变体里 `tsc --noEmit` 都进 CI——它是全项目级。

## JVM——独立二进制 vs 构建工具

Java/Kotlin 仓库通常已有 gradle 或 maven，JVM 惯例是 format/lint 活在构建里（spotless、ktlint-gradle、detekt）。每次 commit 跑 JVM 启动要数秒——绝不把 `./gradlew` 挂进 pre-commit。

**推荐**：构建里已有 spotless（或等价物）就完全不加 format hook——CI 跑 `spotlessCheck`/`detekt` 把门。只有当仓库有 JVM 文件但*没有*构建系统、或用户明确要 commit 时做 per-file 格式化，才接独立二进制（google-java-format jar、ktlint CLI）。

## php / dart——没有 stdin 的 formatter

`php-cs-fixer` 的 stdin 模式吐 unified diff 而不是修复后源码；`dart format` 干脆没有 stdin flag。都进不了 git-format-staged。

**推荐**：当原地 fixer hook——改写工作区文件并失败一次，用户 re-add 再提交（markdownlint-cli2 同款 UX）。和 check hook 失败的代价一样，但文件已经替你修好了。仓库本来就用 prettier 且 PHP 是少数派时，`@prettier/plugin-php` 可以省掉第二个 formatter。

## Agent 入口——.claude/skills 软链 vs 入库实体

**推荐**：软链布局——`AGENTS.md` + `.agents/skills/` 入库，`.claude/skills` 为 gitignore 的目录级软链（→ `../.agents/skills`），由 `scripts/agent-links.sh` 重建。Claude Code ≥2.1.277 经内置 agents-md 插件原生读 `AGENTS.md`（需 `instructionFiles=claude-md-and-agents-md`，旧版 CC 才需要 `CLAUDE.md` 软链——本机统一走新版，不再挂），指令侧不需要任何软链或副本；skill 发现仍走 `.claude/skills`，所以只剩这一条链。理由：仓库保持工具中立（AGENTS.md 是跨 harness 惯例）、skill 只维护一份、Windows clone 不会被入库软链坑（git 在没有 `core.symlinks` 时把软链落成文本文件——入库软链对所有人是坏文件，gitignore 的本机软链只需要在创建它的机器上工作）。

入库实体 `.claude/skills/` 只当退路：协作者在 Windows 上 clone 且没有开发者模式软链支持、又不愿跑脚本——那种情况双份内容会漂移，所以仍然优先教会他们跑 `scripts/agent-links.sh`。

## Secrets 态势

**推荐**：gitleaks 作为唯一 secret 门，`protect` 模式扫暂存 diff。历史已提交 secret 用 `regexTarget = "line"` 的精确值放行——放行正则匹配的是*行*内容，锚在辨识度高的值上。绝不按路径放行（那个文件里再有真泄漏就哑了），也不用 `.gitleaksignore` 的行号指纹（下次重排就烂）。仓库自有凭据格式（env 文件、面板配置）写自定义 `[[rules]]` 块 + 占位符放行。真实凭据只存在于 gitignored env 文件——第一次开 hook 的提交之前确认 `.gitignore` 盖住了它们。

## Lint 严重度——先修后挂

**推荐**：跑每个配方的验证命令全仓检查，修完所有发现，提交，*然后*门才生效。绝不靠降严重度或加排除让 hook 过——门只有反映仓库真实状态才是诚实的。用户拒绝修也不要悄悄装 hook：明说哪些文件下次提交会被拦，让他们选。唯一的例外模式是生成/三方代码——那种用诚实的 `exclude:`/`files:` 划出去，并注释为什么。

## hook 框架——什么时候不用 pre-commit + gfs

这套栈唯一真正的绝活是 gfs 格式化*暂存内容*：未暂存 WIP 不被碰、commit 不被格式化阻断。替代品：

- **husky + lint-staged**——JS 原生，跑之前 stash 未暂存改动。目标相同但机制更重（部分暂存时 stash/restore 会竞态）。团队全 JS 且已有 husky 时选。
- **lefthook**——单二进制、并行、语言无关、基于工作区。pre-commit 的 python 依赖是反对理由时选。
- **pre-commit 官方 `repo:` hooks**（`mirrors-*`、`ruff-pre-commit`……）——每个工具在隔离环境里跑、版本锁定。跨机器工具版本漂移是真问题时选；代价是丢掉 brew 同源的简单和 per-tool 配置复用。

pre-commit + gfs 仍是默认：唯一直接格式化 index 的方案，且一个框架统一覆盖所有语言。
