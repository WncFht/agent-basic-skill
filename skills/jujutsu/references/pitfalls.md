# Common JJ Pitfalls for Agents

Use this file as a preflight checklist when a JJ repo looks unusual, when you
are tempted to reach for Git muscle memory, or when a command route feels
uncertain.

## Critical Mistakes

### 1. Using Git Mutations in a JJ-First Repo

Problem:

- `git add`, `git commit`, `git rebase`, `git stash`, and `git push` bypass the
  workflow this skill is meant to protect.

Safer route:

```bash
jj st
jj diff
jj commit -m "message"
```

### 2. Treating Detached HEAD as a Problem to Fix

Problem:

- In colocated JJ/Git repos, `git status` often reports detached HEAD.
- That is normal and should not trigger `git checkout`.

Safer route:

```bash
jj st
jj bookmark list
```

### 3. Reusing a Dirty Shared Workspace

Problem:

- Mixing unrelated work into someone else's working-copy commit creates hard to
  unwind history.

Safer route:

```bash
jj workspace add ../repo-agent-fix --name agent-fix -r @- -m "Your task"
```

### 4. Forgetting That `jj commit` Creates the Next Working Copy

Problem:

- After `jj commit -m ...`, `@` is usually the next empty change, not the
  finished one you just described.

Safer route:

- Inspect with `jj st`.
- Push the finished parent with `jj git push --change @-` if appropriate.

### 5. Guessing at Rebase Modes

Problem:

- `-b`, `-s`, and `-r` do different things, and using the wrong one rewrites
  the wrong set of revisions.

Safer route:

- `-b` for a branch relative to destination
- `-s` for a revision plus descendants
- `-r` for only the specified revision

Test selection with `jj log -r ...` first if the graph is not obvious.

## Common Confusions

### There Is No Staging Area

- JJ tracks file changes automatically.
- If you only want part of the current diff in the commit, prefer
  `jj commit <paths> -m ...` or another explicit non-interactive route.

### Bookmarks Are Not "Current Branch"

- JJ has no active branch concept matching Git.
- Bookmarks are named refs that may point at your current change, or may not.

### Change IDs Can Diverge

- If `jj log` shows `abcxyz/0` and `abcxyz/1`, the logical change diverged.
- Use commit IDs or the suffixed change ID to be explicit.

### Conflicts Can Be Deferred, But Not Forgotten

- JJ can keep conflicted revisions visible while you continue other work.
- That does not mean the conflict resolved itself. Come back intentionally.

### `jj restore` Preserves the Revision

- `jj restore path` undoes content changes but keeps the revision and metadata.
- If you meant to drop the whole revision, that is closer to `jj abandon`.

## Quick Checklist

- [ ] I ran `jj st` before mutating anything.
- [ ] I am not about to use `git add`, `git commit`, `git stash`, or `git push`.
- [ ] I know whether I am reusing this workspace or creating a new one.
- [ ] I know whether the target revision is `@`, `@-`, or a named bookmark.
- [ ] I checked whether `jj commit` or `jj squash` is the correct rewrite.
- [ ] I have a recovery path such as `jj op log` or `jj undo` in mind if this goes wrong.
