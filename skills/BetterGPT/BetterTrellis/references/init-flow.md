# Init Flow

## Goal

把 Trellis 的接入判断和初始化代操作流程固定下来，避免每次都临场拼命令。

## Step 1: Check CLI

先确认本机可用：

```bash
trellis --version
```

如果命令不存在，先明确告知用户需要先安装 CLI。

官方安装方式：

```bash
npm install -g @mindfoldhq/trellis@latest
```

## Step 2: Check Project State

进入项目根目录后，检查：

- Trellis 基础：
  - `.trellis/`
  - `AGENTS.md`
  - `.agents/skills/`
- Codex 自动接入：
  - `.codex/config.toml`
  - `.codex/hooks/session-start.py`
  - `.codex/hooks.json`

但在 **Windows 原生 Codex** 下，要额外区分：

- hooks 配置位是否存在
- hooks 当前平台是否真的支持并执行

默认不要把这两件事当成同一件事。

判定规则：

- 如果 `trellis` CLI 可用，且 `.trellis/` 已存在  
  → 判定为 **Trellis 基础可用**
- 如果基础项存在，但 `.codex/*` 不完整  
  → 判定为 **Trellis 可用，但 Codex 自动接入不完整**
- 如果基础项和 `.codex/*` 都完整  
  → 判定为 **Trellis for Codex 自动接入完整**
- 只有在 `.trellis/` 与基础接入物都明显缺失时  
  → 判定为 **未初始化**

Windows 原生 Codex 补充口径：

- 即使 `codex_hooks = true` 已开启，只要当前平台 hooks 仍未实际支持  
  → 也不要把 `hooks.json` 缺失直接判定成“当前 Trellis 不可用”
- 这时更准确的说法是：  
  → **Trellis 基础可用 / Codex workflow 可用，但 hooks 仍属于占位或未来兼容项**

## Step 3: Ask Before Init

如果判定为未初始化，不直接执行。

使用固定语义：

> 检测到当前项目尚未完成 Trellis 初始化，是否现在为当前项目执行初始化？
> 将执行：`trellis init --codex -u <name>`
> 初始化完成后，通常需要重开当前项目会话，Trellis 的 hooks / skills / agents 才会完整接入。

只有在用户明确回复“是 / 确认 / 继续”后，才继续。

## Step 4: Init Command

在项目根目录执行：

```bash
trellis init --codex -u <name>
```

如果用户没有指定名字，Trellis 默认可从 `git config user.name` 推断，但在代操作场景下，优先使用用户明确给出的名字。

## Step 5: Post-Init Check

初始化后，回读以下结果：

- `.trellis/` 是否已生成
- `AGENTS.md` 是否已生成或更新
- `.agents/skills/` 是否存在
- `.codex/config.toml` 是否存在
- `.codex/hooks/session-start.py` 与 `.codex/hooks.json` 是否存在

还要提醒用户检查全局 `~/.codex/config.toml`：

```toml
[features]
multi_agent = true
codex_hooks = true
```

如果 hooks 未启用，就要说明：Trellis 基础结构虽然已经落地，但 SessionStart 自动注入能力不会完整生效。

如果当前是 Windows 原生 Codex，还要额外说明：

- 当前应优先按 `AGENTS.md` + skills + 文档驱动 workflow 理解实际生效路径
- `codex_hooks = true` 与 hooks 文件更适合作为未来兼容位或占位，不应直接宣称“hooks 已在当前平台生效”
