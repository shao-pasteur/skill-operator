# AGENTS.md

This repo manages AI agent skills. Skills are grouped by purpose; each category is a plugin that installs through a marketplace in Claude Code, Codex, Copilot CLI and Cursor. Web apps use zips that CI packages.

## What you may edit

- Everything under `plugins/<category>/skills/<skill>/`: `SKILL.md` plus the optional `scripts/`, `references/` and `assets/`
- `categories.yaml`: the category list

## Files you must not edit by hand

`make build` generates these. Hand edits are overwritten on the next build, and `make check` reports them:

- `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`, `.cursor-plugin/marketplace.json`
- `plugins/*/.claude-plugin/plugin.json`, `plugins/*/.codex-plugin/plugin.json`, `plugins/*/.cursor-plugin/plugin.json`
- The part of `README.md` between `<!-- catalog:start -->` and `<!-- catalog:end -->`

## After every change

```bash
make build && make check
```

Fix every error from `make check`. Warnings may stay when there is a reason.

## Skill format rules

- Frontmatter uses only the Agent Skills standard fields: `name`, `description`, `license`, `compatibility`, `metadata`
- `name`: lowercase letters, digits and single hyphens, at most 64 characters, the same as the folder name, unique across the repo
- `description`: 1–1024 characters, saying what the skill does and when to use it, with no leftover `TODO`
- `compatibility`: only when the skill has scripts or environment requirements, at most 500 characters
- `metadata.web`: the string `"true"` or `"false"`, saying whether web apps can use the skill. Required when the skill has `scripts/`
- The folder decides the category; do not put the category in the frontmatter
- Keep `SKILL.md` under 500 lines and move details into `references/`

## Personal information (this is a public repo)

- Never write absolute home paths (`/Users/<name>/`, `/home/<name>/`, `C:\Users\<name>\`), account names, email addresses or API keys
- Read personal values from environment variables or `~/.config/<skill-name>/`, and say in `SKILL.md` which settings are needed and what to tell the user when they are missing
- Use placeholders in examples, such as `/Users/<you>/...`

## Common commands

| Command | What it does |
|---|---|
| `make new CATEGORY=<category> NAME=<name>` | Create a new skill from the template |
| `make import SRC=<path> CATEGORY=<category>` | Copy an existing skill in and validate it |
| `make build` | Generate the manifests and the README catalog |
| `make check` | Validate every skill and generated file |
| `make package` | Package web zips into `dist/` |
| `make test` | Run the tests for `scripts/` |
| `make hooks` | Install the pre-commit hook |
