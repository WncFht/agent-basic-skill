# Init Flow

Use this only when a project may need Trellis initialization or Codex integration repair.

## Check CLI

```bash
trellis --version
```

If missing, tell the user Trellis CLI is required:

```bash
npm install -g @mindfoldhq/trellis@latest
```

## Check Project State

From the project root, inspect only what is needed:

- `.trellis/`
- `AGENTS.md`
- `.agents/skills/`
- `.codex/agents/`
- `.codex/skills/`
- `.codex/hooks/`

Only inspect hook internals when diagnosing hook behavior:

- `.codex/hooks/session-start.py`
- `.codex/hooks.json`
- global Codex feature flags

Status wording:

- `.trellis/` exists -> Trellis base is available.
- base exists but `.codex/*` is incomplete -> Trellis is usable, Codex integration files are incomplete.
- base and Codex directories exist -> Codex integration files appear complete.
- base is missing -> not initialized.

Do not equate integration files with active hook runtime. Hook support needs compatible platform behavior, enabled feature flags, and runtime evidence.

## Ask Before Init

Do not initialize silently. Ask once and name the command:

```bash
trellis init --codex -u <name>
```

Proceed only after explicit user confirmation.

## Post-Init Check

After init, verify the expected files above. If hook behavior matters, also check global feature flags:

```toml
[features]
multi_agent = true
codex_hooks = true
```

Treat feature flags as required setup, not proof that a hook ran. Report base availability, Codex integration-file status, and hook runtime evidence separately.
