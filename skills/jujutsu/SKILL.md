---
name: jujutsu
description: "**REQUIRED** - Activate first for any VCS work in jj-enabled repos. Trigger when `.jj/` exists, repo docs require `jj`, or the user explicitly asks for jj commands. Work JJ-first, prefer dedicated workspaces for parallel tasks, avoid interactive flows, and create bookmarks late."
allowed-tools: Bash(jj *)
---

# Jujutsu (jj) for Agents

Use this skill whenever a repository contains `.jj/`, project docs say to use
`jj`, or the user explicitly asks for Jujutsu commands. In a jj-enabled repo,
JJ is the source of truth even if a colocated `.git/` directory also exists.

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
   and work there instead of reusing it.

5. **Do not panic about detached HEAD in colocated repos.**
   In a repo with both `.jj/` and `.git/`, Git often shows detached HEAD. That
   is normal under JJ and is not something to "fix" with `git checkout`.

6. **Create bookmarks late.**
   Bookmarks are coordination refs, not the unit of local editing. Prefer
   pushing by change ID or naming a bookmark only when the user wants to share
   work or keep a stable branch name.

7. **Escalate into references only when needed.**
   Keep this main file for route selection and safe defaults. Read
   `references/commands.md`, `references/revsets.md`,
   `references/pitfalls.md`, or `references/advanced.md` only for the specific
   scenario you are handling.

## Core Concepts

### The Working Copy Is a Commit

Your working directory is always the working-copy commit `@`. There is no
staging area. File edits become part of `@` automatically.

### Commits Are Mutable

JJ expects you to rewrite and refine commits freely. A clean history comes from
editing, squashing, absorbing, or rebasing changes instead of piling up fixup
commits.

### Workspaces Are JJ's Isolation Tool

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

### Change IDs and Commit IDs Are Different

- **Change ID** identifies the evolving logical change and stays stable across
  rewrites.
- **Commit ID** changes whenever the commit is rewritten.
- When a change diverges, prefer commit IDs or the suffixed change notation
  shown by `jj log` such as `abcxyz/0`.

### Conflicts and Undo Behave Differently from Git

- JJ records conflicts in commits. They do not force an immediate stop unless
  your current task demands resolution right away.
- `jj undo` and `jj op log` are first-class recovery tools. Prefer them over
  Git reflog-style recovery in JJ repos.

## Recommended Workflow

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
- If JJ reports a stale workspace, run `jj workspace update-stale` before doing
  anything else.

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
- `jj commit path/to/file -m` keeps only selected paths in the current commit
  and moves the remaining changes into the new working-copy commit on top

### 4. Edit and Refine

During implementation:

```bash
jj diff
jj log
jj show @
```

Common refinement commands:

```bash
# Rewrite only the current change description
jj describe -m "Refine provider timeout handling"

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
# Keep only the selected files in the current commit, leave the rest for follow-up
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

## Reference Routing

Read the matching file only when it helps with the task:

- `references/commands.md`
  Use for Git-to-JJ intent mapping, quick command lookup, and push/bookmark
  patterns.
- `references/revsets.md`
  Use when writing or reviewing `-r` expressions and commit selection logic.
- `references/pitfalls.md`
  Use as a preflight checklist when the repo is confusing, conflicted, or the
  correct JJ route is unclear.
- `references/advanced.md`
  Use for multi-remote setups, divergent changes, operation-log recovery,
  conflict follow-up, or colocated Git/JJ details.

## Colocated Git Repos

Practical rules:

- Use JJ for normal agent work.
- Treat Git detached HEAD as expected.
- Avoid `git add`, `git commit`, `git rebase`, `git stash`, and `git push`
  unless the user explicitly asks to use Git.
- If a Git-only tool changed refs, run `jj st` or another JJ command so JJ can
  import the updated view.

## Common Agent Mistakes

- Treating JJ like Git with a staging area
- "Fixing" detached HEAD in a colocated repo
- Reusing a dirty shared workspace instead of creating a new one
- Creating bookmarks too early and then forgetting they do not auto-advance
- Running editor-opening or TUI commands in a non-interactive environment
- Using a revset or rebase mode by guess instead of checking the relevant
  reference file or `jj help`
