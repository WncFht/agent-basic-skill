# Path Rendering

Use the shortest path that still lets the user identify the file.

## Priority

1. File name
2. Project-relative path
3. Absolute path

Prefer file names or relative paths in ordinary summaries. Use absolute paths only when required by platform rules, explicit user request, ambiguity, multi-workspace context, or precise evidence.

## File Names

Use file names when the directory is obvious and names are unique:

```text
Updated:
- SKILL.md
- routing.md
```

## Relative Paths

Use relative paths when module location matters or file names are ambiguous:

```text
Updated:
- BetterLanguage/references/path-rendering.md
- BetterSubagents/references/agent-registry.md
```

## Commands And Logs

Keep commands, log text, config keys, API names, and product names literal. Do not translate them.

Prefer:

```text
`python .trellis/scripts/task.py list` returned `0 task(s)`.
```

Avoid repeating a full absolute path beside a command unless the path itself is the issue.

## Final Check

- Can the user find the file?
- Did a path become longer than needed?
- Did any command, key, log, or product name get translated?
