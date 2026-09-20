# Memory Skill

`memory-skill` is the runtime and workflow contract for Codex-managed agent
memory repos. It gives the agent one consistent way to:

- initialize or adopt a memory repo
- resolve the active memory root
- sync before reading and after writing
- keep writes small, curated, and publishable
- survive real-world GitHub sync issues with proxy-aware git execution

Chinese README: [README.zh-CN.md](./README.zh-CN.md)

## What This Repo Owns

This repository is the skill implementation, not the memory data itself.

- Skill repo: `~/.codex/skills/memory-skill`
- Memory repo: usually `~/.codex/memory`
- Saved active-root pointer: `~/.codex/state/memory-skill/state.json`

The runtime creates and manages the memory repo, but the memory content lives
in that separate git repo tree.

## Install

This skill now ships inside [`agent-basic-skill`](https://github.com/WncFht/agent-basic-skill):

```bash
git clone git@github.com:WncFht/agent-basic-skill.git
python agent-basic-skill/scripts/install_skill.py memory-skill
```

If you are replacing an older local install under another folder name, remove
the old copy first so Codex only sees one active `memory-skill`.

## First Run

Create or adopt a memory repo before the first sync:

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh --memory-root ~/.codex/memory
```

Or adopt an existing valid memory repo:

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh \
  --memory-root ~/.codex/memory \
  --adopt
```

Once a repo has been initialized or adopted, the runtime stores the active root
in `~/.codex/state/memory-skill/state.json`.

## Mental Model

Think in terms of read rounds and write batches.

- A read round starts with `pre-read`, then opens one or more memory files from
  that synchronized snapshot.
- A write batch updates one or more memory files that belong to the same
  logical change, then publishes them with `post-write`.
- Memory is curated working knowledge for future tasks, not a transcript and
  not a dumping ground.

## Typical Flow

### 1. Before reading memory

Run:

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh pre-read
```

If the memory repo is valid and clean, the runtime:

- resolves the active memory root
- acquires a repo lock
- fetches and fast-forwards when an upstream exists
- leaves local-only repos untouched

### 2. Read the smallest useful set first

Start with:

- `core.md`
- the current machine summary
- the current repo summary, if the repo resolves cleanly

Only expand to topic packs or repo detail packs when the task actually needs
them.

### 3. Write back durable findings

Write only information that is stable and likely to help future sessions:

- durable user preferences
- machine-specific environment facts
- repo-specific workflows
- cross-repo operational knowledge

### 4. Publish the write batch

Run:

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh post-write
```

When a remote is configured, `post-write` will:

- create a commit if there are staged changes
- fetch the remote
- rebase onto upstream when needed
- push the current branch

If no remote exists, it still creates the local commit and keeps the repo
consistent.

## Active Memory Root Resolution

The runtime resolves the active memory root in this order:

1. `--memory-root <path>`
2. `MEMORY_ROOT`
3. `~/.codex/state/memory-skill/state.json`
4. default `~/.codex/memory`

## Memory Layout

- `core.md`: defaults that should influence most sessions
- `rules.md`: curation policy and scope rules
- `machines/`: machine summaries and repo path maps
- `repos/`: repo summaries and detail packs
- `topics/`: cross-repo or cross-tool reusable knowledge

Index files route the runtime. Packs hold the actual curated memory.

## Command Reference

### Initialize a new memory repo

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh \
  --memory-root ~/.codex/memory \
  --branch main
```

### Initialize with a remote

```bash
~/.codex/skills/memory-skill/scripts/init-memory.sh \
  --memory-root ~/.codex/memory \
  --remote git@github.com:your-org/agent-memory.git
```

### Sync before reading

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh pre-read
```

### Resolve the current machine hostname

```bash
~/.codex/skills/memory-skill/scripts/resolve-machine.sh
```

Use `--json` if you also want the raw hostname and which detection path was
used. Prefer this entrypoint over shelling out to `hostname`; some runtimes do
not provide that command, and the runtime already normalizes `.local` and case
for machine routing.

### Sync after writing

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh post-write
```

### Use a specific commit message for a write batch

```bash
~/.codex/skills/memory-skill/scripts/sync-memory.sh post-write \
  -m "docs(memory): record archbox proxy setup"
```

## Network, Auth, and Remote Sync

Real machines do not always have clean GitHub SSH access. The runtime now
handles that reality explicitly.

### What the runtime does

- Tries the configured GitHub transport first, before applying fallback overrides
- Can retry GitHub SSH remotes through one or more SOCKS proxies without overriding every git command globally
- Supports GitHub token-based HTTPS fallback when SSH is unavailable
- Auto-detects common local SOCKS proxies when you do not configure one
- Produces friendlier sync errors with actionable fixes

### Supported auth-related environment variables

| Variable | Purpose |
| --- | --- |
| `MEMORY_SYNC_GITHUB_TOKEN` | Preferred token for private GitHub repo access |
| `GITHUB_TOKEN` | Fallback GitHub token |
| `GH_TOKEN` | Additional fallback GitHub token |

### Supported proxy-related environment variables

| Variable | Purpose |
| --- | --- |
| `MEMORY_SYNC_SOCKS_PROXY` | Explicit SOCKS proxy such as `socks5://127.0.0.1:7897` |
| `ALL_PROXY` / `all_proxy` | Used when already present in the environment |
| `MEMORY_SYNC_DISABLE_LOCAL_PROXY_AUTODETECT=1` | Disables built-in local proxy auto-detection |

If no explicit proxy is set, the runtime will try common local SOCKS endpoints
currently used by many desktop setups:

- `socks5://127.0.0.1:7897`
- `socks5h://127.0.0.1:7891`

### Sync tuning environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEMORY_SYNC_HEARTBEAT_SECONDS` | `2.0` | Lock heartbeat interval |
| `MEMORY_SYNC_STALE_AFTER_SECONDS` | `30.0` | Stale lock threshold |
| `MEMORY_SYNC_WAIT_TIMEOUT_SECONDS` | `300.0` | Lock wait timeout |
| `MEMORY_SYNC_WAIT_POLL_SECONDS` | `0.2` | Lock polling interval |

## Troubleshooting

### Resolving the current machine fails because `hostname` is missing

Do not depend on the shell `hostname` command for memory routing. Use:

```bash
~/.codex/skills/memory-skill/scripts/resolve-machine.sh
```

If you still need a shell-only fallback, prefer:

```bash
uname -n
```

### `pre-read` says the repo has uncommitted changes

`pre-read` only trusts a clean worktree. Commit or discard the changes, or run
`post-write` first if those edits should be preserved.

### GitHub SSH fails with connection closed or timed out

Use one of these approaches:

- let the runtime try direct SSH first, then local SOCKS-assisted SSH automatically
- export `MEMORY_SYNC_SOCKS_PROXY`
- make sure a local SOCKS proxy is available on a common port
- export `MEMORY_SYNC_GITHUB_TOKEN` for HTTPS fallback to private repos

### The runtime says it cannot read stale memory

That is intentional. If sync fails for reasons other than “repo does not exist
yet”, the caller should stop and surface the reason instead of pretending the
old snapshot is current.

### `post-write` fails because git identity is missing

Configure git once:

```bash
git config --global user.name "your-name"
git config --global user.email "you@example.com"
```

### I want a deeper runbook

See [docs/sync-and-troubleshooting.md](./docs/sync-and-troubleshooting.md).

## Development

Run the runtime tests:

```bash
python -m unittest discover -s ~/.codex/skills/memory-skill/tests -p 'test_memory_runtime.py'
```

The shell and PowerShell wrappers all delegate to the same Python runtime so
behavior stays aligned across Linux, macOS, and Windows.

## License

MIT
