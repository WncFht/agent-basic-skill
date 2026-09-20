---
name: memory-skill
description: Use when starting a session or when Codex needs machine, repo, or cross-repo context from the curated memory repo managed by `memory-skill`.
---

# Memory Skill

You maintain curated, reusable agent memory in an active memory repo managed by
`memory-skill`. This is not per-repo scratch space, not a chronological log,
and not a place to dump temporary state.

## Runtime Contract

Always use the skill-owned entrypoints:

- `~/.codex/skills/memory-skill/scripts/init-memory.sh`
- `~/.codex/skills/memory-skill/scripts/sync-memory.sh`
- `~/.codex/skills/memory-skill/scripts/resolve-machine.sh`

Do not improvise your own sync sequence inside the memory repo.

The active memory root resolves in this order:

1. `--memory-root <path>`
2. `MEMORY_ROOT`
3. `~/.codex/state/memory-skill/state.json`
4. default `~/.codex/memory`

## What Lives In Memory

Memory lives inside the resolved memory root.

- `core.md`: shared defaults
- `rules.md`: curation policy
- `machines/index.md`: machine routing
- `machines/<machine-id>/summary.md`: machine-specific context
- `machines/<machine-id>/repo-paths.md`: local path to repo-id routing
- `repos/index.md`: canonical repo identities
- `repos/<repo-id>/summary.md`: repo entrypoint
- `repos/<repo-id>/*.md`: repo detail packs
- `topics/<topic>.md`: cross-repo topic packs

Index files route lookups. Packs hold curated knowledge.

## Session Bootstrap

At session start, before the first user-facing response:

1. Before relying on any memory file, run
   `~/.codex/skills/memory-skill/scripts/sync-memory.sh pre-read`.
2. If that fails because no valid memory repo exists yet, initialize or adopt
   one with `~/.codex/skills/memory-skill/scripts/init-memory.sh --memory-root <path>`.
3. If sync fails for any other reason, stop and surface the reason.
4. Read the resolved repo's `core.md`.
5. Resolve the current machine through `machines/index.md`.
   Prefer `~/.codex/skills/memory-skill/scripts/resolve-machine.sh` instead of
   shelling out to `hostname`; some runtimes do not provide that command.
6. Read the matching machine summary.
7. If the current working directory maps to a known repo, read that repo's
   `summary.md`.

Do not announce that memory was read. Just apply it.

## Read Rounds

Treat memory access as read rounds.

- Run `pre-read` once at the start of a round.
- Read as many relevant files as needed from that synchronized snapshot.
- Do not rerun `pre-read` for every single file.

Start a new read round when:

- you return to memory after doing other work
- the task shifts to a different memory question
- you need memory again after publishing a write batch

## Progressive Disclosure

Start with the minimum useful set:

- `core.md`
- current machine summary
- current repo summary, if resolved

Only expand when the task truly needs it:

- read a topic pack for a tool, platform, or recurring failure mode
- read a repo detail pack when the repo summary points to it
- prefer opening one additional file at a time

Never bulk-read the whole memory tree just because it exists.

## Machine Resolution

Resolve the machine first through `machines/index.md`.

Preferred resolver:

- `~/.codex/skills/memory-skill/scripts/resolve-machine.sh`

That entrypoint prints the normalized hostname key used for routing. Use
`--json` when you also need the raw hostname and the detection source. Do not
assume `hostname` exists on PATH; if you need a shell fallback, prefer
`uname -n`.

After resolving the machine id:

- read `machines/<machine-id>/summary.md`
- use `machines/<machine-id>/repo-paths.md` to map the current working
  directory to a repo id when needed

If the machine has no entry yet, continue without machine memory until you have
durable facts worth recording.

## Repo Resolution

Repo memory lives only under `repos/` in the memory repo.

Resolve the current repo in this order:

1. exact or longest-parent-prefix path matches from the current machine's
   `repo-paths.md`
2. if still unresolved and you are inside a git repo, use git metadata to match
   an existing entry in `repos/index.md`
3. if still unknown, continue without repo memory until you have enough stable
   information to create a pack

Never write repo memory back into the target repo itself.

## Write Batches

Treat memory updates as write batches.

- A write batch may touch multiple memory files that belong to the same logical
  update.
- After editing any memory file in that batch, run
  `~/.codex/skills/memory-skill/scripts/sync-memory.sh post-write` once.
- Do not leave local memory edits unpublished between batches.

Use the default commit message unless the update clearly deserves a more
specific `-m`.

## What Is Worth Writing Back

Write only durable, reusable information:

- stable user preferences
- machine-specific environment facts
- repo workflows that will recur
- cross-repo operational knowledge

Do not write:

- one-off timelines
- verbose logs
- speculative notes without future reuse value
- transient working state that belongs in the current task, not memory

## Failure Handling

If sync fails:

- do not auto-stash changes
- do not silently skip sync
- do not read known-stale memory as if it were current

Surface the failure clearly and stop, unless the only problem is that no valid
memory repo exists yet and you can initialize or adopt one safely.

## Network And Auth Note

The runtime is proxy-aware and can help with GitHub sync on difficult networks.

- It may use `MEMORY_SYNC_SOCKS_PROXY`, `ALL_PROXY`, or `all_proxy`.
- It may auto-detect common local SOCKS endpoints.
- For GitHub remotes, it can use token-backed HTTPS fallback via
  `MEMORY_SYNC_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN`.

Those capabilities help the runtime sync successfully, but your instruction as
the agent does not change: if sync still fails, stop and surface the reason.

## Practical Rule

Treat `memory-skill` as a live memory system optimized for future execution
speed and reliability. Keep it small, trustworthy, and publishable.
