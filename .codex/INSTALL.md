# Installing agent-basic-skill for Codex

Enable this skill bundle in Codex via native skill discovery. Clone the repo and symlink its `skills/` directory.

## Prerequisites

- Git
- Python 3.11+ if you plan to use the optional managed installer

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/WncFht/agent-basic-skill.git ~/.codex/agent-basic-skill
   ```

2. **Create the skills symlink:**
   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/agent-basic-skill/skills ~/.agents/skills/agent-basic-skill
   ```

   **Windows (PowerShell):**
   ```powershell
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
   cmd /c mklink /J "$env:USERPROFILE\.agents\skills\agent-basic-skill" "$env:USERPROFILE\.codex\agent-basic-skill\skills"
   ```

3. **Restart Codex** (quit and relaunch the CLI) so it discovers the bundle.

4. **Optional: sync bundled local agents into Codex:**
   ```bash
   mkdir -p ~/.codex/agents
   rsync -a ~/.codex/agent-basic-skill/agents/ ~/.codex/agents/
   ```

   This repo ships reusable local agent profiles such as `code-mapper`,
   `docs-researcher`, `browser-debugger`, `reviewer`, `search-specialist`,
   `frontend-developer`, `refactoring-specialist`, `explorer`, `worker`, and
   `shell-script-expert`.

## Optional Managed Install

If you want managed copies under `~/.codex/skills` instead of, or in addition to, native discovery, run the repo installer:

```bash
cd ~/.codex/agent-basic-skill
python scripts/install_skill.py memory-skill
python scripts/install_skill.py paper-note-skill plot-skill report-download
```

This installer replaces `~/.codex/skills/<skill-name>` with the current repo copy.

## Migrating from Older Copies

If you previously copied individual skills into `~/.codex/skills`, native discovery through `~/.agents/skills/agent-basic-skill` is now the preferred bundle-level install.

If the same skill exists both in the symlinked bundle and in `~/.codex/skills`, remove stale duplicates when practical so future sessions do not pick up an unexpected old copy.

## Verify

Check that native discovery points to the bundle:

```bash
ls -la ~/.agents/skills/agent-basic-skill
```

You should see a symlink or junction pointing to `~/.codex/agent-basic-skill/skills`.

Check that the bundled skills exist:

```bash
ls ~/.agents/skills/agent-basic-skill
```

Expected entries: `memory-skill`, `paper-note-skill`, `plot-skill`, `report-download`.

If you synced local agents, verify one of them too:

```bash
test -f ~/.codex/agents/code-mapper.toml && echo OK
```

## Updating

```bash
cd ~/.codex/agent-basic-skill && git pull
```

The symlinked bundle updates immediately after the pull. Restart Codex if the current session has already cached the old skill list.

## Uninstalling

```bash
rm ~/.agents/skills/agent-basic-skill
```

Optionally delete the clone:

```bash
rm -rf ~/.codex/agent-basic-skill
```
