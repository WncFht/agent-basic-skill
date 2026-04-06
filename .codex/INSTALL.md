# Installing agent-basic-skill for Codex

Enable this skill bundle in Codex via native skill discovery. Clone the repo and symlink its `skills/` directory.

## Prerequisites

- Git
- Python 3.11+ if you plan to use the optional managed installer or wrapper bootstrap helpers

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

## Thin Wrapper Prerequisites

Native skill discovery exposes the skill docs immediately, but wrapper skills still need their external runtime repos or local workspaces before first real use.

Prepare only the wrappers you actually plan to use:

| Skill | External repo / workspace | Default path(s) | Env var(s) |
|-------|----------------------------|-----------------|------------|
| `bilinote-video-note` | `WncFht/BiliNote` | `~/Desktop/src/BiliNote` or `~/Desktop/src/BiliNote/backend` | `BILINOTE_REPO`, `BILINOTE_BACKEND_ROOT` |
| `paperflow-pipeline-notes` | `WncFht/paperflow`, `research-notes` workspace | `~/Desktop/src/paperflow`, `~/Desktop/src/research-notes` | `PAPERFLOW_REPO`, `RESEARCH_NOTES_ROOT` |
| `shuiyuan-cache-skill` | `WncFht/shuiyuan_exporter` | `~/Desktop/src/shuiyuan_exporter` | `SHUIYUAN_EXPORTER_REPO` |
| `bilibili-up-digest` | `WncFht/PulseDeck` | `~/Desktop/src/PulseDeck` | `BILIBILI_UP_DIGEST_REPO` |
| `video-note-render-pdf-v0` | `WncFht/video-note-pipeline`, repo-local `video-notes` workspace | `~/Desktop/src/video-note-pipeline`, `<runtime_repo>/.local/workspaces/video-notes` | `VIDEO_NOTE_PIPELINE_REPO`, `VIDEO_NOTE_WORKSPACE_ROOT` |
| `video-note-render-pdf-v1` | `WncFht/video-note-pipeline`, repo-local `video-notes` workspace | `~/Desktop/src/video-note-pipeline`, `<runtime_repo>/.local/workspaces/video-notes` | `VIDEO_NOTE_PIPELINE_REPO`, `VIDEO_NOTE_WORKSPACE_ROOT` |
| `video-note-render-pdf-v2` | `WncFht/video-note-pipeline`, repo-local `video-notes` workspace | `~/Desktop/src/video-note-pipeline`, `<runtime_repo>/.local/workspaces/video-notes` | `VIDEO_NOTE_PIPELINE_REPO`, `VIDEO_NOTE_WORKSPACE_ROOT` |

If you prefer local overrides instead of the default paths, write them to:

```bash
mkdir -p ~/.codex/state/agent-basic-skill
cp ~/.codex/agent-basic-skill/local/source-overrides.example.json \
  ~/.codex/state/agent-basic-skill/source-overrides.json
```

Then edit `~/.codex/state/agent-basic-skill/source-overrides.json` and point each source id to your real local path.

## Optional Managed Install

If you want managed copies under `~/.codex/skills` instead of, or in addition to, native discovery, run the repo installer:

```bash
cd ~/.codex/agent-basic-skill
python scripts/install_skill.py BetterGPT
python scripts/install_skill.py deepresearch-skill
python scripts/install_skill.py bilibili-up-digest shuiyuan-cache-skill video-note-render-pdf-v0 video-note-render-pdf-v1 video-note-render-pdf-v2
```

This installer replaces `~/.codex/skills/<skill-name>` with the current repo copy and, for skills that ship an `external-repos.json`, it checks or clones the required external runtime repo first.

Bundle-native skills can still ship companion assets. For example, `deepresearch-skill` includes a LaTeX report template, agent metadata, and a multimodal-ingestion reference, so install the whole `skills/deepresearch-skill/` directory rather than only `SKILL.md`.

## Migrating from Older Copies

If you previously copied individual skills into `~/.codex/skills`, native discovery through `~/.agents/skills/agent-basic-skill` is now the preferred bundle-level install.

If the same skill exists both in the symlinked bundle and in `~/.codex/skills`, remove stale duplicates when practical so future sessions do not pick up an unexpected old copy.

## Verify

Check that native discovery points to the bundle:

```bash
ls -la ~/.agents/skills/agent-basic-skill
```

You should see a symlink or junction pointing to `~/.codex/agent-basic-skill/skills`.

Check that the main entry skill exists:

```bash
test -f ~/.agents/skills/agent-basic-skill/BetterGPT/SKILL.md && echo OK
```

If you synced local agents, verify one of them too:

```bash
test -f ~/.codex/agents/code-mapper.toml && echo OK
```

For wrapper skills, verify the resolver after preparing the runtime:

```bash
python ~/.agents/skills/agent-basic-skill/video-note-render-pdf-v1/scripts/resolve_video_note_paths.py --json
```

如果你想验证基线版，也可以运行：

```bash
python ~/.agents/skills/agent-basic-skill/video-note-render-pdf-v0/scripts/resolve_video_note_paths.py --json
```

如果你想验证 v2，也可以运行：

```bash
python ~/.agents/skills/agent-basic-skill/video-note-render-pdf-v2/scripts/resolve_video_note_paths.py --json
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
