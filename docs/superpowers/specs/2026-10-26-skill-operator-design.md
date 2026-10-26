# skill-operator design spec

- Date: 2026-10-26 (revised 2026-10-27: repo moved to the `shao-pasteur` organization; repo content translated to English)
- Status: approved and implemented
- Repo: `shao-pasteur/skill-operator` (GitHub, public)

## 1. Goals

Manage my own AI agent skills in one public GitHub repo, so that:

1. **One source serves many AI tools**: each skill is written once in the [Agent Skills open standard](https://agentskills.io/specification) (`SKILL.md`).
2. **CLI and IDE agents install it through marketplace plugins**: Claude Code, Codex, Copilot CLI, Cursor.
3. **Web chat apps get zips to upload**: claude.ai, ChatGPT, Gemini.
4. **Skills are grouped by purpose, and a category is the unit of installation**: each category is a plugin, so you install only the categories you need.

### Success criteria

- On a clean machine, Claude Code, Codex and Copilot CLI can all add the marketplace and **install a single category**, and the installed skills trigger.
- Adding a skill takes only "`make new` → write → commit → push", with no hand-edited JSON.
- After a push, CLIs on other machines receive the update, and web-compatible skills appear as zips in the `latest` release automatically.
- `make check` and CI are green.

## 2. Scope

### In scope

- Skill format rules and validation
- Generating the category settings into every platform's manifests
- Local and CI validation
- Web zip packaging and release publishing
- Install instructions for each platform (README)
- Tools to add and migrate skills (`make new`, `make import`)

### Out of scope (not in the first version)

| Item | Why / how to add it later |
|---|---|
| Gemini CLI | It reads only `gemini-extension.json` and `skills/` at the repo root, which conflicts with one folder per category. To add it later, have the generator also produce a flat root mirror plus `gemini-extension.json`; no restructuring needed |
| Grok | No official skill mechanism |
| An `all` plugin | Codex and Cursor cannot build one without a flat mirror. The README shows a loop that installs several categories instead |
| Skill quality evals | They need API keys and cost money; hook up `skill-creator`'s eval flow once there are more skills |
| Skills in the `meta` category | `AGENTS.md` plus `make new` already cover the need; the category stays but is empty |
| Listing in official directories (Cursor marketplace, the OpenAI plugin directory and so on) | Possible now that the repo is public, but not in the first version |

## 3. Platform support matrix

| Platform | Install method | Manifests it reads | Install by category |
|---|---|---|---|
| Claude Code | marketplace | `.claude-plugin/marketplace.json`, `plugins/<id>/.claude-plugin/plugin.json` | ✅ |
| Codex | marketplace | `.agents/plugins/marketplace.json`, `plugins/<id>/.codex-plugin/plugin.json` | ✅ |
| Copilot CLI | marketplace | `.claude-plugin/marketplace.json` (Copilot reads this path) and the plugin.json in the plugin folder | ✅ |
| Cursor | marketplace | `.cursor-plugin/marketplace.json`, `plugins/<id>/.cursor-plugin/plugin.json` | ✅ |
| claude.ai | upload a zip by hand | — | per skill |
| ChatGPT | upload a zip by hand | — | per skill |
| Gemini | upload a zip or `SKILL.md` by hand | — | per skill |

## 4. Skill format

Follows the Agent Skills open standard exactly, plus a single custom key under `metadata`.

```markdown
---
name: tw-stock-tracker
description: On Taiwan stock trading days… Use when the user asks for…
compatibility: Requires Python 3.11+ and network access
metadata:
  web: "false"
---
(instructions)
```

| Field | Required | Rules |
|---|---|---|
| `name` | yes | 1–64 characters; only `a-z`, `0-9`, `-`; no leading or trailing `-`; no `--`; **must match the folder name**; **unique across the repo** |
| `description` | yes | 1–1024 characters; says what the skill does and when to use it |
| `compatibility` | no | 1–500 characters; only for skills with scripts or environment requirements |
| `license` | no | Falls back to the repo's root `LICENSE` |
| `metadata.web` | depends | `"true"` or `"false"` (a string). Skills without `scripts/` default to `"true"`; **skills with `scripts/` must set it** |
| Platform-specific fields (such as `allowed-tools`) | no | Allowed; validation only warns |

Other rules:

- **The folder decides the category**; the frontmatter does not name it.
- **Skills have no version number** (see section 9).
- Keep `SKILL.md` under 500 lines; details go in `references/`, executables in `scripts/`, templates and data in `assets/`.
- **No personal information** (see section 12). When a skill needs personal settings (such as an Obsidian vault path), read them from environment variables or a config file outside the repo and document them in `SKILL.md`.
- **Repo content is in English.** A skill may still produce output in another language when that is its purpose; `tw-stock-daily-tracker` writes its reports in Traditional Chinese and says so in its `SKILL.md`.

## 5. Categories

Categories are defined in `categories.yaml`, the only settings file maintained by hand. A category `id` is both the plugin name and the skill prefix in Claude (such as `/dev:code-review`), so keep it short. Aim for 5–8 categories.

```yaml
marketplace: skill-operator
owner:
  name: Yuan
  github: shao-pasteur
categories:
  - id: dev
    title: Software development
    description: Code review, debugging, git, testing and architecture design
  - id: writing
    title: Writing and documents
    description: Articles, translation, presentations and document conversion
  - id: research
    title: Research and knowledge management
    description: Looking things up, summarizing and organizing Obsidian notes
  - id: finance
    title: Investing and finance
    description: Taiwan stock tracking, technical analysis and financial report digests
  - id: productivity
    title: Personal productivity
    description: Scheduling and automating daily routines
  - id: meta
    title: Skill management
    description: Tools for creating and checking new skills in this repo
```

A skill belongs to exactly one category; when uses overlap, pick the main one.

## 6. Repo layout

```
skill-operator/
├── categories.yaml                     # maintained by hand
├── plugins/
│   └── <category id>/
│       ├── skills/<skill>/SKILL.md     # maintained by hand (optional scripts/, references/, assets/)
│       ├── .claude-plugin/plugin.json  # generated
│       ├── .codex-plugin/plugin.json   # generated
│       └── .cursor-plugin/plugin.json  # generated
├── .claude-plugin/marketplace.json     # generated
├── .agents/plugins/marketplace.json    # generated
├── .cursor-plugin/marketplace.json     # generated
├── scripts/                            # Python CLI for generating, validating, packaging and scaffolding, plus tests
├── .github/workflows/                  # CI and releases
├── Makefile
├── README.md                           # install instructions + the generated Skill catalog block
├── AGENTS.md                           # repo rules for AI agents
├── CLAUDE.md                           # one line pointing to AGENTS.md
├── LICENSE                             # MIT
├── .gitattributes                      # marks generated files as linguist-generated
└── .gitignore                          # dist/ and so on
```

### Makefile targets

| Command | What it does |
|---|---|
| `make build` | Generate every manifest and the README catalog block from `categories.yaml` and the SKILL.md files |
| `make check` | Run every check in section 8 |
| `make package` | Package web zips into `dist/` |
| `make new CATEGORY=<id> NAME=<name>` | Create a new skill from the template |
| `make import SRC=<path> CATEGORY=<id>` | Copy an existing skill folder into the repo and validate it |
| `make hooks` | Install the git pre-commit hook (build, make sure generated files are staged, then check) |
| `make test` | Run the pytest suite for `scripts/` |

## 7. Generator (`make build`)

- **Technology**: Python 3.11+, run with `uv run`. Dependencies are declared in the root `pyproject.toml` (uv manages the environment, no manual venv). The only runtime dependency is PyYAML (tests also need pytest). The GitHub repo path is built from `owner.github` and `marketplace` in `categories.yaml` (`<owner.github>/<marketplace>`).
- **Input**: `categories.yaml`, plus the frontmatter of every `plugins/*/skills/*/SKILL.md`.
- **Output**:
  - Three plugin.json files per category (Claude, Codex, Cursor), with `name` and `description` from `categories.yaml`.
  - Three marketplace.json files at the root, each in its platform's format, for example:

    Claude (`.claude-plugin/marketplace.json`):
    ```json
    {
      "name": "skill-operator",
      "owner": { "name": "Yuan" },
      "plugins": [
        { "name": "dev", "source": "./plugins/dev", "description": "Code review, debugging, git, testing and architecture design" }
      ]
    }
    ```

    Codex (`.agents/plugins/marketplace.json`):
    ```json
    {
      "name": "skill-operator",
      "interface": { "displayName": "skill-operator" },
      "plugins": [
        {
          "name": "dev",
          "source": { "source": "local", "path": "./plugins/dev" },
          "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
          "category": "Software development"
        }
      ]
    }
    ```
  - The Skill catalog table in the README between `<!-- catalog:start -->` and `<!-- catalog:end -->`: category → skill → one-line description → whether web apps can use it.
- **Rules**:
  - Generated files are committed (every marketplace reads straight from git).
  - Output is deterministic (the same input gives byte-identical output) so CI can compare it.
  - Categories without skills do not appear in the marketplaces and get no plugin.json.
  - Any error (bad YAML, a folder under `plugins/` that is not in `categories.yaml`, unparsable frontmatter) fails immediately and **writes nothing**.
  - No manifest has a `version` (see section 9).

## 8. Validation and CI

### `make check`

**Errors (block the commit and CI):**

| Check | What it covers |
|---|---|
| Standard format | Every field rule in section 4 |
| Repo rules | `name` unique across the repo; category folders must be in `categories.yaml`; skills with `scripts/` must set `metadata.web` |
| File references | Relative paths referenced in SKILL.md (`references/…`, `scripts/…`, `assets/…`) must exist |
| Generated files in sync | Rebuild into memory and compare with the committed files; on a mismatch, tell the user to run `make build` |
| Script syntax | `.py` files are compiled, `.sh` files run through `bash -n` (scripts are never executed) |
| Personal information | Absolute home paths in `plugins/**` (`/Users/<name>`, `/home/<name>`, `C:\Users\<name>`). Placeholders of the form `<…>` do not count |

**Warnings (do not block):** SKILL.md over 500 lines; platform-specific frontmatter fields; `description` under 50 characters; email addresses in `plugins/**`.

### GitHub Actions

| Workflow | Trigger | What it does |
|---|---|---|
| `check.yml` | push, pull request | `make test`, `make check`, a gitleaks secret scan, and `claude plugin validate .` |
| `release.yml` | push to `main` that touches `plugins/**` | See section 10 |

## 9. Versions and updates (CLI platforms)

- No plugin.json or marketplace.json has a `version`. Claude Code then uses the git commit as the version: **a push to `main` is a release**, with no version bumps or tags.
- Cost: every commit makes every category look updated and get copied again; skills are small files, so this is negligible.
- Claude Code's background auto-update is off by default; turn it on once per machine under `/plugin` → Marketplaces after the first install.
- **Fallback**: if Codex, Cursor or Copilot turn out to need a `version` to detect updates, the generator writes a hash of the category's `skills/` content as the version. The version only changes when the content does, so only touched categories update, and nothing is managed by hand.

## 10. Web zip releases

- `make package`: packages every skill whose `metadata.web` is `"true"` (or that defaults to true because it has no `scripts/`) into `dist/<name>.zip`, with a single top-level folder `<name>/` inside. `dist/` is not committed.
- `release.yml`: repackages every zip and replaces the assets of the fixed-tag **`latest` release**. Downloads always live at `https://github.com/shao-pasteur/skill-operator/releases/download/latest/<name>.zip`.
- The release notes list the skills that changed in the push, so you know which to upload again (web apps do not update on their own).
- Where to upload: claude.ai is "Settings → Skills → upload the zip"; ChatGPT and Gemini are added to the README once tested (see section 13).
- If a platform needs a different zip layout (for example `SKILL.md` at the zip root), the packager produces an extra layout for that platform with a platform suffix in the file name.

## 11. Installation and workflows

### Install (README)

The repo is public, so no git credentials are needed.

| Platform | Add the marketplace | Install a category |
|---|---|---|
| Claude Code | `claude plugin marketplace add shao-pasteur/skill-operator` | `claude plugin install dev@skill-operator`; then turn on auto-update under `/plugin` → Marketplaces |
| Codex | `codex plugin marketplace add shao-pasteur/skill-operator` | `codex plugin add dev@skill-operator` |
| Copilot CLI | `copilot plugin marketplace add shao-pasteur/skill-operator` | `copilot plugin install dev@skill-operator` |
| Cursor | Written once tested (see section 13) | — |

Install several categories at once:

```bash
for c in dev writing finance; do claude plugin install "$c@skill-operator"; done
```

### Adding a skill

1. `make new CATEGORY=dev NAME=foo`: creates the `plugins/dev/skills/foo/SKILL.md` template.
2. Write the content (yourself or with an agent; agents follow the rules in `AGENTS.md`).
3. Try it locally: `claude --plugin-dir ./plugins/dev`.
4. `git commit`: the pre-commit hook builds, makes sure generated files are staged and runs the checks.
5. `git push`: CLIs pick it up through updates; web zips are rebuilt automatically.

### Migrating an existing skill

1. `make import SRC=~/.claude/skills/<name> CATEGORY=<id>`: copies and validates it.
2. Fix the validation errors. The most common is a personal path; for example, `tw-stock-daily-tracker` had its Obsidian vault path hardcoded in `SKILL.md` and `scripts/build_report.py` and now reads it from an environment variable.
3. Once the plugin version works, **delete the local copy** so the same skill does not exist twice and trigger by mistake.

### What `AGENTS.md` covers

- Edit only `plugins/*/skills/**` and `categories.yaml`; never hand-edit generated JSON or the README catalog block.
- Run `make build && make check` after changes.
- The skill format rules in section 4 and the personal information rules in section 12.

## 12. Public repo considerations

- **License**: MIT, in the root `LICENSE`.
- **Personal information**: skill content and scripts must not contain absolute home paths, account names, email addresses or API keys. `make check`'s personal information check and the gitleaks scan in CI guard this.
- **Personal settings**: personal values (paths, account names) always come from environment variables or `~/.config/<skill-name>/`, and `SKILL.md` says which settings are needed and how to prompt the user when they are missing.
- **Git history**: check that the history holds no personal information before publishing; gitleaks scans the full history.

## 13. Items verified during implementation

Each item had a fallback decided up front; the results only affect generator or README details, not the overall structure.

| # | Item | Fallback | Result (2026-10-27) |
|---|---|---|---|
| 1 | Cursor's exact marketplace.json and plugin.json formats; how a personal account adds a git marketplace | Generate per the official docs; if personal accounts cannot use marketplaces, the README explains copying skill folders by hand | Left for the user to verify by hand (Cursor is not installed on this machine) |
| 2 | Where Copilot CLI looks for plugin.json inside a plugin folder | Have the generator write an extra copy where Copilot expects it | Verified: Copilot CLI reads the marketplace.json and plugin.json under `.claude-plugin/`; `copilot plugin install finance@skill-operator` installed 1 skill with no login and no extra files |
| 3 | Codex's CLI install command; how it updates without a `version` | Write the tested command into the README; handle updates with the fallback in section 9 | Install verified: `codex plugin marketplace add` + `codex plugin add finance@skill-operator`, reading `.agents/plugins/marketplace.json`. Update behavior without `version` not tested yet; fallback not applied |
| 4 | Where ChatGPT's consumer app uploads skills; whether Gemini accepts zips and in what layout | Produce an extra zip layout per section 10; if Gemini does not take zips, the README says to upload `SKILL.md` directly (only for skills without extra files) | Left for the user to verify by hand (there are no web skills yet, so the release has no zips) |
| 5 | Whether `claude plugin validate` needs a login in CI | If it does, drop it from CI and keep it as an optional local step in `make check` | Verified: no login needed; the CI step stays and passes |
