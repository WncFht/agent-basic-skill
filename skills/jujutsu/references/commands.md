# Jujutsu Command Patterns

Use this reference when the user asks for specific JJ commands or when you need
to translate a Git habit into a JJ-safe workflow. Treat the mappings below as
intent-level guidance, not perfect one-to-one aliases.

## State and History

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| Show working state | `git status` | `jj st` | Primary status view in JJ repos |
| Show current diff | `git diff` | `jj diff` | Compares `@` with its parent(s) by default |
| Show history | `git log` | `jj log` | Add `--graph` when topology matters |
| Show one revision | `git show REV` | `jj show REV` | Useful for finished changes |
| Annotate file history | `git blame file` | `jj file annotate file` | File-level history view |

## Creating and Editing Changes

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| Record all current changes | `git commit -am "msg"` | `jj commit -m "msg"` | In JJ, this also opens a new working-copy commit on top |
| Rename current change | `git commit --amend -m "msg"` | `jj describe -m "msg"` | Changes only the description |
| Move current diff into parent | `git commit --amend` on follow-up work | `jj squash -m "msg"` | Rewrites parent and usually empties current change |
| Start a fresh empty child change | `git checkout -b topic` or new WIP commit | `jj new -m "msg"` | Creates a new working-copy commit |
| Edit an existing revision | `git checkout REV` | `jj edit REV` | Switches the working copy to that change |
| Commit only selected paths | `git add path && git commit` | `jj commit path/to/file -m "msg"` | Keeps selected paths in current commit; remainder goes into new `@` |
| Drop file changes | `git restore file` | `jj restore file` | Restores from parent(s) into `@` by default |

Notes:

- There is no JJ staging area. Do not use `git add`.
- `jj commit` without path arguments is roughly `jj describe` plus `jj new`.
- Prefer `jj commit <paths> -m` over interactive splitting in non-interactive
  agent runs.

## Bookmarks and Change Navigation

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| List local branch-like refs | `git branch` | `jj bookmark list` | Bookmarks are JJ's coordination refs |
| Create bookmark | `git branch name REV` | `jj bookmark create name -r REV` | Defaults to `@` if `-r` is omitted |
| Move bookmark | `git branch -f name REV` | `jj bookmark move name --to REV` | Use when user wants a stable named ref |
| Delete bookmark | `git branch -D name` | `jj bookmark delete name` | Removes local bookmark |
| Track remote bookmark | `git branch -u origin/name` | `jj bookmark track name --remote origin` | Imports remote bookmark as local bookmark |
| View all remotes | `git branch -r` | `jj bookmark list --all-remotes` | Prefer this before raw Git views |

## Rebase, Merge, and History Surgery

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| Rebase a commit and descendants | `git rebase --onto DEST SRC^ BRANCH` | `jj rebase -s SRC -o DEST` | `-s` moves the source revision and descendants |
| Rebase a whole branch relative to destination | `git rebase DEST topic` | `jj rebase -b topic -o DEST` | `-b` means branch-relative selection |
| Rebase only the selected revision | interactive or manual Git sequence | `jj rebase -r REV -o DEST` | Descendants are preserved around the moved revision |
| Create a merge commit | `git merge OTHER` | `jj new @ OTHER` | New working-copy commit with both parents |
| Auto-absorb lines into older commits | manual fixup flow | `jj absorb` | Useful after broad edits touching earlier changes |
| Duplicate a revision | `git cherry-pick REV` | `jj duplicate REV -d @` | Use only when you want a copied change |

Notes:

- `jj rebase` defaults to `-b @` if you do not specify `-b`, `-s`, or `-r`.
- `jj new` can take multiple parents, which is why `jj new @ OTHER` is the
  common merge pattern.
- Avoid interactive surgery unless the user explicitly wants it and the
  environment can support it.

## Push and Remote Patterns

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| Fetch from remote | `git fetch origin` | `jj git fetch --remote origin` | Refresh before pushing |
| Push current work ad hoc | `git push origin HEAD` | `jj git push --remote origin --change @` | Generates a tracked bookmark automatically |
| Push finished parent after `jj commit` | `git push origin HEAD~1` | `jj git push --remote origin --change @-` | Useful when `@` is the next empty change |
| Push named bookmark | `git push origin topic` | `jj git push --remote origin --bookmark topic` | Use when user wants a stable branch name |
| Push everything tracked | `git push --all` | `jj git push --tracked` | Only when the user clearly wants that scope |

Notes:

- In JJ, the push target remote is selected by `--remote`, not by the tracked
  bookmark alone.
- `jj git push --change REV` creates a bookmark automatically using the
  configured template.
- Prefer explicit `--remote origin` in agent runs to avoid ambiguity.

## Recovery and Undo

| Intent | Common Git Habit | JJ Command | Notes |
| --- | --- | --- | --- |
| View mutation history | `git reflog` | `jj op log` | Shows repository operations, not only commit heads |
| Undo last operation | `git reset --hard HEAD@{1}` | `jj undo` | Safer and more direct in JJ |
| Inspect old repo state | reflog + detached checkout | `jj --at-operation OP log` | Non-destructive time travel |
| Abandon unwanted change | `git reset --hard` or drop commit | `jj abandon REV` | Removes the revision from visible history |

## When To Escalate

- Read `references/revsets.md` when `-r` expressions become non-trivial.
- Read `references/pitfalls.md` before guessing at a confusing JJ workflow.
- Read `references/advanced.md` for multi-remote setups, divergence, or
  operation-log recovery.
