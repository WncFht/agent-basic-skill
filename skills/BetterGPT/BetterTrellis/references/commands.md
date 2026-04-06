# Commands

## Install / Init

```bash
npm install -g @mindfoldhq/trellis@latest
trellis --version
trellis init
trellis init -u <name>
trellis init --codex -u <name>
trellis init --cursor
trellis init --claude
```

## Update

```bash
trellis update
trellis update --dry-run
trellis update --force
trellis update --migrate
```

说明：

- `trellis update` 默认只更新未被用户修改过的受管文件
- `--dry-run` 先预览
- `--force` 覆盖所有管理文件
- `--migrate` 处理重命名、删除等结构迁移

## Task Workflow

```bash
python .trellis/scripts/task.py create "user-auth" --assignee <name>
python .trellis/scripts/task.py start <task-id>
python .trellis/scripts/task.py list
python .trellis/scripts/task.py finish
python .trellis/scripts/task.py archive <task-id>
```

## What To Prefer

- 项目还没接入  
  → 优先 `trellis init --codex -u <name>`
- 项目已经接入，但版本或模板过旧  
  → 优先 `trellis update`
- 工作已经需要明确 PRD、上下文、当前任务  
  → 优先 `task.py`

不要把命令表直接整段甩给用户，除非用户明确要速查表。
