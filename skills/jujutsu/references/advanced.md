# Advanced JJ Topics

Use this file only when the task actually needs advanced JJ behavior. The main
skill file should remain enough for day-to-day agent work.

## Colocated JJ and Git Repositories

JJ and Git often share the same repository data:

- `.jj/` and `.git/` can coexist.
- JJ imports and exports to Git-compatible refs automatically.
- Git read-only inspection commands can be tolerated when needed, but prefer JJ
  for any action that mutates history or refs.

Practical consequences:

- Git may show detached HEAD. That is normal.
- Bookmark conflicts can appear after remote fetches or concurrent edits.
- Git-oriented tooling may become confused by conflicted files.

## Workspace Isolation

Useful commands:

```bash
jj workspace list
jj workspace add ../repo-agent-fix --name agent-fix -r main -m "Task name"
jj workspace update-stale
jj workspace forget agent-fix
```

Guidelines:

- Prefer one workspace per human or agent when work may overlap.
- If you remove a workspace directory permanently, follow up with
  `jj workspace forget`.
- Use `--sparse-patterns full` only when you intentionally want a full checkout.

## Operation Log and Undo

JJ's operation log is often the fastest recovery tool after a mistaken rebase,
bookmark move, or abandon.

```bash
jj op log
jj op log -p
jj undo
jj --at-operation <op-id> log
```

Patterns:

- Use `jj undo` for the most recent mistaken operation.
- Use `jj --at-operation <op-id> ...` to inspect old state without changing
  current history first.
- If several mistakes happened, inspect the operation log before trying more
  history surgery.

## Divergent Changes

You may see output such as `mzvwutvl/0` and `mzvwutvl/1` for the same change
ID. That means the logical change has multiple visible commit incarnations.

Typical causes:

- concurrent work in multiple workspaces
- local rewrite plus remote rewrite
- sync/import activity in colocated repos

Common responses:

```bash
# Drop the unwanted incarnation
jj abandon <commit-id>

# Give one side a fresh change ID
jj metaedit --update-change-id <commit-id>

# Inspect both versions before deciding
jj show <commit-id>
```

Prefer explicit commit IDs when resolving divergence.

## Multi-Remote Setups

When a repo uses both `origin` and `upstream`, keep fetch/push intent explicit.

```bash
jj config set --user git.fetch '["upstream", "origin"]'
jj bookmark track main --remote origin
jj bookmark track main --remote upstream
jj git fetch --remote origin
jj git fetch --remote upstream
```

Guidelines:

- Fetch from the remote you care about before rebasing or pushing.
- Push only to the intended remote; do not assume tracked bookmarks imply push
  destination.
- Use remote-qualified bookmark names such as `main@origin` when the distinction
  matters.

## Conflict Follow-Up

JJ can preserve conflicted revisions while you continue other work. When you
return to resolve them:

```bash
jj log
jj new <conflicted-rev> -m "Resolve conflicts"
# edit files
jj resolve path/to/file
jj squash -m "Resolve conflicts"
```

Agent notes:

- `jj resolve` may invoke tooling depending on configuration. Avoid it in a
  non-interactive environment unless you know the path is safe.
- If the environment cannot support conflict tooling, edit conflict markers
  manually and verify with `jj diff`.
