# skill-operator

My own AI agent skills, grouped by purpose. They install as marketplace plugins in Claude Code, Codex, Copilot CLI and Cursor, and web apps get zips to upload.

Each category is a plugin, so you can install only the categories you need. Every skill follows the [Agent Skills open standard](https://agentskills.io/specification) (`SKILL.md`).

## Install

The repo is public, so no git credentials are needed. Replace `<category>` with a category id from the Skill catalog below, such as `finance`.

| Platform | Add the marketplace | Install a category |
|---|---|---|
| Claude Code | `claude plugin marketplace add shao-pasteur/skill-operator` | `claude plugin install <category>@skill-operator` |
| Codex | `codex plugin marketplace add shao-pasteur/skill-operator` | `codex plugin add <category>@skill-operator` |
| Copilot CLI | `copilot plugin marketplace add shao-pasteur/skill-operator` | `copilot plugin install <category>@skill-operator` |
| Cursor | Not verified yet | Not verified yet |

Claude Code 2.1.275 or later can do it in one step: `claude plugin install <category> --marketplace shao-pasteur/skill-operator`.

Install several categories at once:

```bash
for c in dev writing finance; do claude plugin install "$c@skill-operator"; done
```

**Claude Code auto-update** is off by default. After installing, run `/plugin` in Claude Code, open Marketplaces, pick `skill-operator` and choose **Enable auto-update**. Without it, run `claude plugin marketplace update skill-operator` to fetch updates.

## Web apps (claude.ai, ChatGPT, Gemini)

Skills that work in web apps are packaged as zips in the [`latest` release](https://github.com/shao-pasteur/skill-operator/releases/tag/latest):

```text
https://github.com/shao-pasteur/skill-operator/releases/download/latest/<skill-name>.zip
```

After each update, the "Re-upload needed" section of the release notes lists the skills that changed. Web apps do not update on their own, so upload those zips again.

| Platform | How to upload |
|---|---|
| claude.ai | Settings → Skills → upload the zip |
| ChatGPT | Not verified yet |
| Gemini | Not verified yet |

## Skill catalog

<!-- catalog:start -->
### Investing and finance (`finance`)

| Skill | Description | Web apps |
|---|---|---|
| `tw-stock-daily-tracker` | Tracks Taiwan stocks on trading days before the open, during the session (every… | — |

### Workflow (`workflow`)

| Skill | Description | Web apps |
|---|---|---|
| `sharron` | Works the Sharron way: plans before acting, delegates to subagents with clear b… | — |
<!-- catalog:end -->

## Development

You need [uv](https://docs.astral.sh/uv/) and GNU Make. The rules are in [AGENTS.md](AGENTS.md).

```bash
make hooks                                         # install the pre-commit hook (once after cloning)
make new CATEGORY=dev NAME=my-skill                # create a new skill from the template
make import SRC=~/.claude/skills/foo CATEGORY=dev  # import an existing skill
make build                                         # generate the manifests and the README catalog
make check                                         # validate skills and generated files
make package                                       # package web zips into dist/
make test                                          # run the tests for scripts/
```

Try a category locally without pushing:

```bash
claude --plugin-dir ./plugins/<category>
```

To add a category, edit `categories.yaml` and run `make build`. Categories without skills do not appear in the marketplace.
