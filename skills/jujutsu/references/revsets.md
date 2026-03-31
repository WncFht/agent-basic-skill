# Jujutsu Revset Quick Reference

Use this file when you need to write or review `jj log -r ...`,
`jj diff -r ...`, `jj show ...`, or any other command that selects revisions by
revset.

## Basic Pattern

```bash
jj log -r '<revset>'
```

Quote revsets in shell commands so operators such as `|` and `&` are not
interpreted by the shell.

## Common Symbols

| Revset | Meaning |
| --- | --- |
| `@` | Current working-copy commit |
| `@-` | Parent of the working-copy commit |
| `@--` | Grandparent of the working-copy commit |
| `root()` | Repository root commit |
| `main` | Commit currently pointed to by bookmark `main` |
| `main@origin` | Remote bookmark `main` on remote `origin` |
| `trunk()` | Configured trunk alias if the repo or user config defines it |

## Common Operators

| Operator | Meaning | Example |
| --- | --- | --- |
| `::` | Ancestor or descendant range, depending on position | `::@` ancestors of `@`; `main::` descendants of `main` |
| `..` | Exclude the left side's ancestors | `main..@` commits reachable from `@` but not from `main` |
| `|` | Union | `main | @` |
| `&` | Intersection | `visible_heads() & bookmarks()` |
| `~` | Difference | `@ ~ main` |
| `-` | Parent shorthand | `@-` |

## High-Value Functions

| Function | Meaning |
| --- | --- |
| `all()` | All visible revisions |
| `bookmarks()` | All local bookmarks |
| `remote_bookmarks()` | All remote bookmarks |
| `parents(x)` | Parents of `x` |
| `children(x)` | Children of `x` |
| `ancestors(x)` | Ancestors of `x` |
| `descendants(x)` | Descendants of `x` |
| `latest(x, n)` | Most recent `n` revisions within `x` |
| `merges()` | Merge revisions |
| `mutable()` | Mutable local revisions |
| `empty()` | Revisions with no file changes |
| `file(path)` | Revisions touching a file |
| `author(name)` | Revisions by matching author |
| `description(text)` | Revisions whose description matches text |
| `date(expr)` | Date-filtered revisions |

## Practical Queries

```bash
# Current ancestry chain
jj log -r '::@'

# Commits unique to the current work relative to main
jj log -r 'main..@'

# Latest positions of all bookmarks
jj log -r 'bookmarks()'

# All visible heads
jj log -r 'visible_heads()'

# Most recent five visible revisions
jj log -r 'latest(all(), 5)'

# Commits touching a specific path
jj log -r 'file("src/server/provider.ts")'

# Merge revisions only
jj log -r 'merges()'

# Mutable local revisions
jj log -r 'mutable()'

# Remote main versus local main
jj log -r 'main@origin | main'
```

## Agent Notes

- Prefer bookmarks or explicit revision IDs over broad revsets when the user is
  asking about one concrete change.
- If a revset is unclear, test it with `jj log -r '<revset>'` before using it
  in a mutating command.
- When a repo uses remote bookmarks heavily, `name@remote` is often clearer
  than relying on local tracking behavior.
