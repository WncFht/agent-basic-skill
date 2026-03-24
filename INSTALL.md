# Install agent-basic-skill

## Local repository workflow

Use the bundled installer script when this repository exists locally.

Install one skill:

```bash
python scripts/install_bundle.py --skill jupyter-notebook --dest "$HOME/.codex/skills"
```

Install or refresh the full bundle:

```bash
python scripts/install_bundle.py --all --dest "$HOME/.codex/skills"
```

List the bundle contents without copying files:

```bash
python scripts/install_bundle.py --all --list
```

## Update an existing local installation

After pulling the latest repository changes, rerun the same install command. The installer replaces the destination skill directory with the repository copy, so the refresh path is:

```bash
git pull
python scripts/install_bundle.py --all --dest "$HOME/.codex/skills"
```

For a single-skill refresh:

```bash
git pull
python scripts/install_bundle.py --skill pdf --dest "$HOME/.codex/skills"
```

## Future GitHub / skill-installer workflow

After publishing this repository to GitHub, single-skill installs can reuse the existing `skill-installer` GitHub repo/path flow.

Set your Codex home:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
```

Install one skill from the published repository:

```bash
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo <owner>/agent-basic-skill \
  --path skills/jupyter-notebook
```

Install the full bundle from the published repository:

```bash
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo <owner>/agent-basic-skill \
  --path skills/pdf \
  --path skills/report-download \
  --path skills/git-commit \
  --path skills/jupyter-notebook \
  --path skills/frontend-slides
```

This preserves each skill as its own install unit while still letting the repository act as a bundled source.
