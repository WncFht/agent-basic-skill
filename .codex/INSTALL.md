# Installing agent-basic-skill

Install each active skill directly under the shared `~/.agents/skills/<name>/` directory. The new skills use this layout for dependency checks and calls between skills.

## Prerequisites

- Git
- Python 3.11+

## Installation

Clone the repository, then install the recommended bundle:

```bash
git clone https://github.com/WncFht/agent-basic-skill.git ~/src/agent-basic-skill
cd ~/src/agent-basic-skill
python scripts/install_skill.py asr figure-viz link-get paper-search video-render-pdf setup-toolchain skill-management document-writing conventional-commits --dest-root ~/.agents/skills
```

The installer replaces each named destination directory. Save local changes before updating. If these skills already exist in `~/.agents/skills`, update only the ones you intend to replace. Avoid installing duplicate copies under `~/.codex/skills`.

Installation copies instructions, scripts, templates, references and bundled assets. It does not install external tools, virtual environments or ASR models. Follow each skill's `SKILL.md` and `deps.toml` to set up dependencies. Restart the agent session to refresh its skill list.

Optional local agent profiles for Codex:

```bash
mkdir -p ~/.codex/agents
rsync -a agents/ ~/.codex/agents/
```

## Updating

```bash
cd ~/src/agent-basic-skill
git pull --ff-only
python scripts/install_skill.py asr figure-viz link-get paper-search video-render-pdf setup-toolchain skill-management document-writing conventional-commits --dest-root ~/.agents/skills
```

The installer retains `$CODEX_HOME/skills` as its default destination for compatibility; explicitly pass `--dest-root` for the shared layout.

## Archived skills

`memory-skill`, `paper-note-skill`, `plot-skill`, `report-download`, `frontend-design` and `diagram-design` are preserved under `vendor/`. They are excluded from the active bundle and cannot be installed by name with the installer. Use `figure-viz` for chart work.

Older installations may have a bundle symlink at `~/.agents/skills/agent-basic-skill`. Remove that symlink after verifying the direct installations, so each skill has one active entry. Previously installed copies of retired skills are not removed automatically.

## Verify

```bash
test -f ~/.agents/skills/asr/SKILL.md
test -f ~/.agents/skills/figure-viz/agents/openai.yaml
test -f ~/.agents/skills/link-get/scripts/link-get
```

## Optional skills excluded from the default Codex installation

`peer-sessions` is distributed in `skills/` but omitted from the installation commands above. See [vendor/README.md](../vendor/README.md) for archived skills excluded from installation.
