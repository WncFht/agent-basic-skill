# Slidev Skill for Codex

Agent skill that helps Codex understand and work with [Slidev](https://sli.dev) presentations.

## Installation

Install from this repo with the standard installer:

```bash
python scripts/install_skill.py slidev
```

If you want to install directly from GitHub into `~/.codex/skills`, use:

```bash
python "$CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py" \
  --repo antfu/skills \
  --path skills/slidev
```

## What's Included

The Slidev skill provides Codex with knowledge about:

- **Core Syntax** - Markdown syntax, slide separators, frontmatter
- **Animations** - Click animations, transitions, motion effects
- **Code Features** - Line highlighting, Monaco editor, code groups, magic-move
- **Diagrams** - Mermaid, PlantUML, LaTeX math
- **Layouts** - Built-in layouts, slots, global layers
- **Presenter Mode** - Recording, timer, remote access
- **Exporting** - PDF, PPTX, PNG, SPA hosting

## Usage

Once installed, Codex can use Slidev knowledge when:

- Creating new presentations
- Adding slides with code examples
- Setting up animations and transitions
- Configuring themes and layouts
- Exporting presentations

### Example Prompts

```
Create a Slidev presentation about TypeScript generics with code examples
```

```
Add a two-column slide with code on the left and explanation on the right
```

```
Set up click animations to reveal bullet points one by one
```

```
Configure the presentation for PDF export with speaker notes
```

## Documentation

- [Slidev Documentation](https://sli.dev)
- [Theme Gallery](https://sli.dev/resources/theme-gallery)
- [Showcases](https://sli.dev/resources/showcases)

## License

MIT
