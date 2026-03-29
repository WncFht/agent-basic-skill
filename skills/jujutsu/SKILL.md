---
name: jujutsu
description: "**REQUIRED** - Activate first for any VCS work. If `.jj/` exists, treat the repo as JJ-first: prefer `jj workspace` for parallel human/agent tasks, treat Git detached HEAD as normal, and create bookmarks late when pushing or preparing a named branch."
allowed-tools: Bash(jj *)
---

# Jujutsu (jj) for Agents

This skill teaches the agent how to work in JJ-first repositories without
falling back to Git habits that create confusion or mix unrelated work.

**Tested with jj v0.39.0.** Command details can change across JJ releases, so
prefer checking `jj help <command>` if behavior looks unfamiliar.

## Agent Contract

When a repository contains `.jj/`, follow these rules first:

1. **Use JJ as the source of truth.**
   Prefer `jj` for status, diff, log, change creation, rebasing, bookmarks,
   fetch, and push. Only use Git when the user explicitly asks for Git or a
   Git-only tool is unavoidable.

2. **Use non-interactive commands.**
   Always pass `-m` when a message is needed. Avoid editor- or TUI-based flows
   such as `jj split`, `jj squash -i`, `jj resolve`, or any command that would
   wait for interactive input.

3. **Run `jj st` before and after mutations.**
   This confirms the working-copy commit you are editing and catches conflicts,
   stale workspaces, or accidental rewrites early.

4. **Prefer a separate workspace over a shared working directory.**
   If the current workspace has unrelated changes, appears to belong to another
   human/agent, or the task may run in parallel, create a new `jj workspace`
   and work there instead of reusing the current directory.

5. **Do not panic about detached HEAD in colocated repos.**
   In a repo with both `.jj/` and `.git/`, Git often shows detached HEAD. That
   is normal under JJ and is not something to "fix" with `git checkout`.

## Core Concepts

### The Working Copy Is a Commit

Your working directory is always the working-copy commit `@`. There is no
staging area. File edits become part of `@` automatically.

### Commits Are Mutable

JJ expects you to rewrite and refine commits freely. A clean history comes from
editing, squashing, absorbing, or rebasing changes instead of piling up fixup
commits.

### Workspaces Are JJ's Worktree-Style Isolation Tool

`jj workspace` is the standard way to give each human or agent an isolated
working copy while still sharing one repository history. For parallel tasks,
prefer **one workspace per actor or task**.

### Bookmarks Are Coordination Refs, Not "The Current Branch"

Bookmarks are the Git-compatible refs you eventually push. They are useful for
sharing or naming work, but they are **not** the main unit of local editing.

For agent work:

- start with commits and workspaces
- create bookmarks late
- push by change ID or by bookmark only when the user wants the work shared

Bookmarks follow rewritten commits, but they do **not** automatically jump to a
new descendant just because you created one.

## Recommended Agent Workflow

### 1. Inspect Before Editing

Start with:

```bash
jj st
jj workspace list
jj bookmark list
```

Interpret the result before editing:

- If `@` is empty and clearly dedicated to your task, you may reuse it.
- If `@` already contains your previous finished task, start a fresh change
  with `jj new -m "Next task"`.
- If `@` contains unrelated changes or may belong to someone else, create a new
  workspace instead of mixing work.

### 2. Create a Dedicated Workspace When Needed

For parallel work, a workspace is usually better than editing in place.

```bash
jj workspace add ../repo-agent-fix --name agent-fix -r main -m "Fix provider timeout handling"
cd ../repo-agent-fix
jj st
```

Use this when:

- the current workspace is dirty with unrelated work
- a human is actively using the main checkout
- multiple agents may touch the repo concurrently
- you want an easy cleanup boundary after the task

Useful commands:

```bash
jj workspace list
jj workspace update-stale
jj workspace forget agent-fix
```

Notes:

- New workspaces inherit sparse patterns by default.
- If JJ reports a stale workspace, run `jj workspace update-stale`.
- `jj workspace forget` stops tracking a workspace after you have removed or
  retired that checkout.

### 3. Start the Task by Naming the Change

If you are reusing the current empty working-copy commit:

```bash
jj describe -m "Fix provider timeout handling"
```

If you want a fresh empty change on top of the current one:

```bash
jj new -m "Fix provider timeout handling"
```

Practical rule:

- `jj describe -m` labels the current `@`
- `jj new -m` creates a new empty `@` on top
- `jj commit -m` finalizes the current change and opens a fresh empty `@`

### 4. Edit and Refine

During implementation:

```bash
jj diff
jj log
jj show @
```

Common refinement commands:

```bash
# Move current changes into the parent commit
jj squash -m "Refine provider timeout handling"

# Automatically move lines to the commits that last touched them
jj absorb

# Drop unwanted file changes from the working-copy commit
jj restore path/to/file.ts
```

For agent-safe splitting, prefer non-interactive patterns instead of `jj split`.

Example:

```bash
# Finalize the current subset into a described commit and continue on the rest
jj commit src/server/provider.ts -m "Fix provider timeout handling"
```

### 5. Push Late

Only push when the user asked for it.

Before pushing:

```bash
jj git fetch --remote origin
jj st
```

For ad hoc agent work, prefer pushing by change:

```bash
# Push the current change by generating a tracked bookmark name automatically
jj git push --remote origin --change @
```

If you already ran `jj commit -m ...` and now the working-copy commit is the
next empty change, push the finished parent instead:

```bash
jj git push --remote origin --change @-
```

If the user wants a stable branch name, create or move a bookmark explicitly:

```bash
jj bookmark create fix/provider-timeout -r @
jj git push --remote origin --bookmark fix/provider-timeout
```

If the bookmark already exists and needs to point at the current change:

```bash
jj bookmark move fix/provider-timeout --to @
jj git push --remote origin --bookmark fix/provider-timeout
```

## Reading "Branches" in JJ

Users often say "branch" when they really mean one of three different things.
Interpret carefully:

- **Local JJ branch-like refs**: `jj bookmark list`
- **All remote bookmarks**: `jj bookmark list --all-remotes`
- **Raw Git remote branches**: `git branch -r` only if the user explicitly
  wants the Git view

In JJ repos, start with bookmarks before assuming Git branch output is the
right answer.

## Colocated Git Repos

In a colocated repo, JJ and Git share the same underlying history but expose it
differently.

Practical rules:

- Use JJ for normal agent work.
- Treat Git detached HEAD as expected.
- Avoid `git add`, `git commit`, `git rebase`, `git stash`, and `git push`
  unless the user explicitly asks for Git.
- If a Git-only tool changed refs, run `jj st` or another JJ command so JJ can
  import the updated view.

## Conflicts and Recovery

### Conflicts

JJ can represent conflicted commits. For agents, do not start an interactive
conflict resolver.

Instead:

1. inspect `jj st`
2. edit conflicted files directly
3. remove conflict markers carefully
4. run `jj st` again until the conflict is resolved

### Undo

If a JJ operation was wrong:

```bash
jj undo
```

To inspect recent repository operations:

```bash
jj op log
```

`jj undo` is often the fastest recovery path after an accidental rebase,
abandon, squash, or bookmark move.

## Quick Reference

| Task | Command |
| --- | --- |
| Status | `jj st` |
| Show workspaces | `jj workspace list` |
| Add isolated workspace | `jj workspace add ../repo-task --name task -r main -m "Task"` |
| Refresh stale workspace | `jj workspace update-stale` |
| Name current change | `jj describe -m "Task"` |
| Start fresh change | `jj new -m "Task"` |
| Finalize current change and open next | `jj commit -m "Task"` |
| Diff | `jj diff` |
| Show current change | `jj show @` |
| Restore file | `jj restore path/to/file` |
| Squash into parent | `jj squash -m "Message"` |
| Absorb lines into older commits | `jj absorb` |
| List bookmarks | `jj bookmark list` |
| List all remote bookmarks | `jj bookmark list --all-remotes` |
| Create named bookmark | `jj bookmark create name -r @` |
| Move named bookmark | `jj bookmark move name --to @` |
| Fetch remote state | `jj git fetch --remote origin` |
| Push current change with auto bookmark | `jj git push --remote origin --change @` |
| Push named bookmark | `jj git push --remote origin --bookmark name` |
| Undo last JJ operation | `jj undo` |
| Inspect operation history | `jj op log` |

## Default Heuristics for Agents

When you need a fast decision, use these defaults:

1. If `.jj/` exists, stay in JJ unless the user explicitly asks for Git.
2. If the current workspace is not obviously yours, create a new workspace.
3. One task should live in one JJ change.
4. Name the change early, create the bookmark late.
5. Use `jj git push --change ...` for ad hoc sharing and named bookmarks only
   when a stable branch name matters.
6. If JJ says the workspace is stale, update it instead of improvising with
   Git.
7. After every mutating command, verify with `jj st`.
