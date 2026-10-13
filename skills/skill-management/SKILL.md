---
name: skill-management
description: 维护本机三 CLI（Claude Code / Codex / Kimi Code）共用的 skills + AGENTS.md 体系：~/.agents 唯一事实源、软链布局、全局与仓库两级 skill 的增删改与同步、命名冲突与加载失效诊断。当用户要新增/安装/更新/删除 skill、同步仓库与全局副本、排查 skill 或 AGENTS.md 没生效、或体检整套体系时使用。
---

# Skill 管理体系

三家 CLI 共享同一份内容，靠**一个事实源 + 软链**做到零漂移。本 skill 是这套体系的维护手册：`scripts/skill_doctor.sh` 一键体检，其余各节是布局图、实测加载矩阵、规则和操作流程。

## 布局

```
~/.agents/                 ← 全局唯一事实源（普通目录，入库无关）
  AGENTS.md                ← 全局用户指令（三家共用同一份）
  keybindings.json         ← CC 键位配置（~/AGENTS.md 同级，机器间 rsync 同步）
  skills/                  ← 全局 skill 集合（活目录：任何子目录三端立刻加载）
    <name>/agents/openai.yaml  ← 跨 harness 界面元数据（必需，见规则 6）
  incubator/               ← 孵化区：开发中/评估中/暂时下线的 skill
                             三家 CLI 只扫 skills/，兄弟目录天然隐身，不入 skill 列表

~/AGENTS.md                → .agents/AGENTS.md          （家目录兜底；也是 CC 全局指令入口）
~/.claude/AGENTS.md        → ../.agents/AGENTS.md       （目前无 CLI 读取，占位保留）
~/.claude/keybindings.json → ../.agents/keybindings.json（CC 键位配置入口）
~/.claude/skills           → ../.agents/skills          （CC 用户级 skill 目录）
~/.codex/AGENTS.md         → ../.agents/AGENTS.md       （codex 全局指令）
~/.kimi-code/AGENTS.md     → ../.agents/AGENTS.md       （kimi 全局指令）

仓库内（需要三家共用的 repo）：
  AGENTS.md                入库，唯一入口——不要与同目录 CLAUDE.md 共存
                           （both 模式双注入漂移；fallback 模式 CLAUDE.md 遮蔽整条 AGENTS.md 链）
  .agents/skills/          入库，仓库级 skill
  .claude/skills           → ../.agents/skills          （gitignored 软链，仅 CC 需要）
```

指令文件永远改 `~/.agents/AGENTS.md` 或仓库 `AGENTS.md` 本体，不改软链端。

## 实测加载矩阵（2026-09-20，`claude -p` 无头探针复验）

| 位置                         | CC 2.1.278                                     | codex 0.154  | kimi 0.42     |
| ---------------------------- | ---------------------------------------------- | ------------ | ------------- |
| 仓库 `AGENTS.md`             | ✓ 原生（≥2.1.277，内置 agents-md 插件）        | ✓            | ✓             |
| 仓库 `.agents/skills/`       | ✗ 需 `.claude/skills` 软链                     | ✓            | ✓             |
| `~/.agents/AGENTS.md` 经软链 | ✓ 经 `~/AGENTS.md`（project 级，需 both 模式） | ✓            | ✓             |
| `~/.agents/skills` 经软链    | ✓（整目录软链可行）                            | ✓ 原生直读   | ✓ 原生直读    |
| `~/.codex/skills`            | —                                              | ✓ codex 私有 | —             |
| `~/.kimi-code/skills`        | —                                              | —            | ✓（目前为空） |

关键行为：

- **CC ≥2.1.277 由内置 agents-md 插件管指令文件**（官方仓库 `mods/agents-md`），`/config` → "Project instructions" 四档：`claude-md`；`claude-md-or-agents-md`（默认 fallback：从 `/` 到 cwd 的祖先路径上存在任一 `CLAUDE.md`/`.claude/CLAUDE.md`/`CLAUDE.local.md`，整条 AGENTS.md 链都不加载）；`claude-md-and-agents-md`（两者都读，软链指向或内容相同的去重）；`managed-only`。本机两台均设 `both`：`settings.json` → `pluginConfigs."agents-md@builtin".options.instructionFiles`。
- **CC 的全局指令靠 `~/AGENTS.md` 以 project 级注入**，只对 `~` 子树内的 cwd 生效；`~/.claude/AGENTS.md` 不在祖先路径上、无人读取，`~/.claude/CLAUDE.md` 已于 2026-09-20 退役。fallback 模式下 `~/AGENTS.md` 在有自家 CLAUDE.md 的仓库（cliproxyapi、cli-history-hub）不加载，这是必须 `both` 的原因。
- **同名 skill 全部列出，各家不替你消重**：codex 双列 `~/.agents/skills` 与 `~/.codex/skills` 同名项；kimi 项目级覆盖全局；CC **用户级压过项目级和 builtin**（反直觉）。
- codex 注入仓库根 + CWD 祖先链上的 AGENTS.md，深层目录懒加载、就近优先；kimi 注入项目根 + 按访问路径懒加载子目录。
- skill 启动时只读 frontmatter（name+description）进列表，正文按需加载；CC 插件 skill 以 `plugin:name` 命名空间出现；`disable-model-invocation: true` 的 skill 不出现在模型列表。
- codex 的 `.system/`（imagegen、skill-creator 等 6 个）是内置，不进 `~/.agents`。

## 规则

1. **skill 名全局唯一**。保留名（撞了会被内置/私有副本遮蔽或双列）：
    - CC 内置：`dataviz update-config keybindings-help code-review simplify fewer-permission-prompts loop claude-api workflow-authoring run init security-review`
    - codex `.system`：`imagegen openai-docs plugin-creator review-agent skill-creator skill-installer`
    - kimi：`import-from-cc-codex init mcp-config`
2. `~/.codex/skills/` 是 **codex 私有区**，只放 codex 专属 skill（本机现有 apple-reminders、chronicle、ical-cli）。**不要放与全局同名的副本**——codex 会把同名 skill 双列，且副本会漂移（2026-09 曾清掉一份落后 7 周的 plot-skill 副本，归档在 `~/.codex/skills-archive/`）。不要把它并入 `~/.agents`。
3. 仓库 `AGENTS.md` 与 `CLAUDE.md` 不同存：both 模式下两者同时注入成双事实源漂移，fallback 模式下 CLAUDE.md 遮蔽整条 AGENTS.md 链（含 `~/AGENTS.md`）；要 CC 额外行为就写进 AGENTS.md。
4. 全局 skill **只在 `~/.agents/skills/<name>/` 维护一份**，直接改那里；仓库 `.agents/skills/` 只放仓库专属 skill，不与全局同名（曾有的 10 个仓库副本已清，防双列与漂移）。
5. **`incubator/` 是 staging 区**：开发中、外部 vendor 进来待评估、或暂时下线的 skill 放 `~/.agents/incubator/<name>/`。没有 per-skill 开关，「启用/下线」就是 `mv` 进出 `skills/`。doctor 会扫 incubator 做 name/撞名检查但只记 WARN（不影响退出码）；promote 前对应 skill 应当 WARN 清零。vendor 第三方 skill 时提交信息记上游 repo + commit SHA。
6. **每个 skill 目录必须带 `agents/openai.yaml`**——OpenAI 兼容 harness（codex 等）读的界面元数据，与 setup-toolchain 对仓库 `.agents/skills/` 的约定同源。最小格式：

    ```yaml
    interface:
        display_name: "<skill 名>"
        short_description: "<一句话说明>"
    ```

    `default_prompt` 与 `policy.allow_implicit_invocation` 可选。缺失只影响跨 harness 呈现，不阻断加载——doctor 记 WARN 不 FAIL。

## 操作

### 新增全局 skill

在 `~/.agents/skills/<name>/` 直接建。先跑 doctor 确认名字不撞保留名和现有目录；顺手补 `agents/openai.yaml`（规则 6）。CC 经 `~/.claude/skills` 目录软链自动可见，无需逐 skill 挂链。

### 仓库 skill 提升为全局

```bash
rsync -a --delete <repo>/.agents/skills/<name>/ ~/.agents/skills/<name>/
git rm -r <repo>/.agents/skills/<name>   # 只留一份，防双列
```

### 诊断「skill / AGENTS.md 没生效」

- **探针必须让模型回显字面 token**（如在文件里放 `MARKER-FOO-42` 再要求原样回复）。让它从正文语义推断会得到假阴性——实测 CC 对「instructions 提到 Taildrop 吗」类问法回 NONE，但同一文件放字面 marker 即回显成功。前几次"CC 不读 `~/.claude/AGENTS.md`"的误判全是探针措辞问题，文件其实一直在加载。
- **CC 指令文件失效先看档位**：`settings.json` → `pluginConfigs."agents-md@builtin".options.instructionFiles`；fallback 模式下路径上任一真实 CLAUDE.md 会让整条 AGENTS.md 链不加载（含 `~/AGENTS.md` 全局指令）。
- codex 无头探测：`cd <git仓库目录> && codex exec "<prompt>" </dev/null`（非 git 目录或 stdin 未关会挂）。
- CC 无头探测：`claude -p "<prompt>" </dev/null`。
- 先跑 doctor：断链、frontmatter name 与目录名不符、保留名冲突——这三类占失效原因的大头。

## 依赖声明与升级

skill 的外部依赖（CLI 工具、venv、模型文件等）在 skill 根目录 `deps.toml` 声明，`skill-management` 只负责发现与编排，依赖知识留在各 skill 自己手里：

```toml
[[dep]]
name = "yt-dlp"                                  # 必填
check = "command -v yt-dlp"                      # 必填，bash -c，exit 0 = 已装
version = "yt-dlp --version"                     # 可选，首行作版本显示
install = "uv tool install yt-dlp"               # 可选
upgrade = "uv tool upgrade yt-dlp"               # 可选
optional = true                                  # 可选；缺失只 WARN 不计退出码
```

`check/version/install/upgrade` 可写成 `{ linux = "...", darwin = "..." }` 按平台分派；某平台没有对应键时该 dep 在该平台显示 `N/A`，不计缺失也不执行 install/upgrade——平台限定功能（如 CUDA-only）用这个表达，不用写 `optional`。约定：

- **check 只读无副作用**：check/version 命令会被反复跑（check 一次、install/upgrade 后复核一次），不得有安装、写文件等副作用。
- **install/upgrade 幂等**：重复执行安全；已最新时应快速 no-op 退出（参考 `link-get/scripts/install_bbdown.sh` 的 `HEAD==FETCH_HEAD` 短路）。
- **排序按依赖序**：dep 按书写顺序执行，运行时装机工具（如 uv，后续 install 靠它）排最前。
- **只给可独立升级的项写 upgrade**：uv tool、自建 venv、源码构建；pacman/brew 管的系统包只写 install，升级随系统走；需要复杂流程的（如 BBDown 源码构建）把逻辑放 skill 自己的 `scripts/install_*.sh`，manifest 里指向它。命令需要 sudo 时在命令里自带（如 `sudo pacman -S`），扫描器不注入提权。

```bash
python3 ~/.agents/skills/skill-management/scripts/skill_deps.py              # 状态矩阵
python3 ~/.agents/skills/skill-management/scripts/skill_deps.py --upgrade    # 全部 upgrade
python3 ~/.agents/skills/skill-management/scripts/skill_deps.py --install video-render-pdf  # 只补某 skill 缺失项
```

不做无人值守的定时升级：AUR -git 重编、CLI 大版本都可能半途 break，且提权要存密码。要"定期提醒过期"用 check 模式挂 cron 即可。

## 体检

```bash
bash ~/.agents/skills/skill-management/scripts/skill_doctor.sh              # 全局 + 默认仓库（obsidian）
bash ~/.agents/skills/skill-management/scripts/skill_doctor.sh <repo> ...   # 追加/指定要查的仓库
```

检查项：5 条软链完好且指向 `~/.agents`；CC `instructionFiles` 档位为 `both`；每个 SKILL.md 的 frontmatter `name` 与目录名一致；跨位置同名（全局/仓库/codex 私有）；保留名冲突；vault↔全局副本漂移；仓库根 AGENTS.md/CLAUDE.md 共存；`deps.toml` 声明的外部依赖齐全；全局 skill 的 `agents/openai.yaml` 在位（WARN）。WARN 不阻塞，FAIL 需要修。
