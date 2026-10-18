# Memory Skill Sync And Troubleshooting

This document is the operator-facing runbook for `memory-skill`.

It focuses on the part people usually discover only after something goes wrong:
sync semantics, remote behavior, GitHub auth, proxy routing, and failure
recovery.

## 1. Operational Model

There are only two runtime sync operations:

- `pre-read`: make the memory snapshot trustworthy before reading
- `post-write`: publish a finished write batch

The runtime intentionally refuses to “just keep going” on stale memory when the
sync step fails. That is a feature, not a bug.

## 2. What `pre-read` Actually Does

`pre-read` validates the memory repo, then:

1. checks that the worktree is clean
2. acquires the repo lock
3. detects the upstream branch
4. fetches the remote if one exists
5. fast-forwards local state to upstream

If the repo has no upstream branch:

- with no remote: it reports a clean local-only repo
- with a remote but no tracking branch: it reports that no fetch was required

## 3. What `post-write` Actually Does

`post-write`:

1. stages all changed files
2. creates a commit when there is something to commit
3. fetches upstream when needed
4. rebases onto upstream
5. pushes the branch

If the repo has a remote but no upstream yet, `post-write` bootstraps upstream
tracking by pushing with `-u`.

## 4. Remote Strategy

The runtime supports three common cases.

### Local-only memory repo

- no remote configured
- sync stays fully local
- useful for single-machine setups

### Normal tracked remote

- standard fetch / fast-forward / rebase / push flow
- no special auth fallback needed

### GitHub remote with hostile network conditions

This is the case that usually hurts the most in practice.

The runtime now helps in three ways:

1. it tries the configured GitHub transport first
2. it can retry GitHub SSH remotes through one or more SOCKS proxies
3. it can fall back to GitHub HTTPS auth when SSH is unavailable

## 5. Proxy Behavior

Proxy resolution order:

1. `MEMORY_SYNC_SOCKS_PROXY`
2. `ALL_PROXY`
3. `all_proxy`
4. local auto-detection unless disabled

Local SOCKS auto-detection only runs when no generic proxy environment is
already configured. If you have already exported `HTTP_PROXY`,
`HTTPS_PROXY`, `ALL_PROXY`, or their lowercase variants, the runtime treats
that as an intentional proxy setup and will not inject an extra SOCKS-based
`GIT_SSH_COMMAND` on top of it.
The runtime does not blindly inject auto-detected proxies into every git call.
For GitHub remotes it prefers:

1. configured transport as-is
2. SOCKS-assisted GitHub SSH retries, one proxy candidate at a time
3. GitHub HTTPS fallback, plus proxy-assisted HTTPS retries when needed
Current built-in local auto-detection targets:

- `socks5://127.0.0.1:7897`
- `socks5h://127.0.0.1:7891`

If auto-detection gets in your way, disable it:

```bash
export MEMORY_SYNC_DISABLE_LOCAL_PROXY_AUTODETECT=1
```

If you want deterministic behavior, set the proxy explicitly:

```bash
export MEMORY_SYNC_SOCKS_PROXY=socks5://127.0.0.1:7897
```

Use `MEMORY_SYNC_SOCKS_PROXY` when you explicitly want SSH-over-SOCKS even on
machines that already export HTTP or HTTPS proxy variables.

## 6. GitHub Auth Fallback

When the remote points at GitHub and SSH transport fails, the runtime can retry
using HTTPS plus a token. If local SOCKS proxies were auto-detected, the runtime
can also retry that HTTPS fallback through those proxies one by one.

Supported token variables, in priority order:

1. `MEMORY_SYNC_GITHUB_TOKEN`
2. `GITHUB_TOKEN`
3. `GH_TOKEN`

Recommended setup for private memory repos:

```bash
export MEMORY_SYNC_GITHUB_TOKEN=ghp_your_token_here
```

The token should have access to the private memory repo. If your environment
already uses a git credential helper, that is also fine.

## 7. Common Failure Modes

### Resolving the current machine via `hostname` fails

Meaning:

- the shell environment does not provide a `hostname` command

Fix:

- use `~/.codex/skills/memory-skill/scripts/resolve-machine.sh`
- add `--json` if you also need the raw hostname and detection source
- if you truly need a shell-only fallback, prefer `uname -n`

### `Memory repo ... has uncommitted changes`

Meaning:

- `pre-read` will not trust a dirty worktree

Fix:

- publish those edits with `post-write`
- or discard them if they should not exist

### `Fetching from origin failed`

Meaning:

- the runtime could not produce a fresh remote snapshot

Likely causes:

- GitHub SSH transport is blocked
- no proxy is available
- HTTPS fallback reached GitHub but has no credentials
- remote host resolution is failing

Fix order:

1. let the runtime exhaust direct SSH, proxy-assisted SSH, and HTTPS fallback once
2. set `MEMORY_SYNC_SOCKS_PROXY` if you know the exact working proxy
3. confirm the proxy actually works
4. export `MEMORY_SYNC_GITHUB_TOKEN` for private GitHub repos
5. retry `pre-read`

### `Timed out waiting for the sync lock`

Meaning:

- another sync process still owns the repo lock

Fix:

- wait for it to finish
- or inspect the owner details and terminate the stuck process if needed

### `Committing memory changes failed`

Meaning:

- git identity or repository state prevented commit creation

Fix:

```bash
git config --global user.name "your-name"
git config --global user.email "you@example.com"
```

## 8. Practical Recipes

### Initialize a new repo with a GitHub remote

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh \
  --memory-root ~/.codex/memory \
  --remote git@github.com:your-org/agent-memory.git
```

### Adopt an existing repo

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh \
  --memory-root ~/.codex/memory \
  --adopt
```

### Run a manual sync with explicit proxy and token

```bash
export MEMORY_SYNC_SOCKS_PROXY=socks5://127.0.0.1:7897
export MEMORY_SYNC_GITHUB_TOKEN=ghp_your_token_here
~/.codex/skills/memory-skill/scripts/sync-memory.sh pre-read
```

### Publish a write batch with a specific message

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh post-write \
  -m "docs(memory): add proxy troubleshooting notes"
```

## 9. Documentation Map

- [README.md](../README.md): user-facing overview and quickstart
- [README.zh-CN.md](../README.zh-CN.md): Chinese overview and quickstart
- [SKILL.md](../SKILL.md): instructions that Codex should follow
