# Platforms: verified facts

What sharron may rely on for Claude Code, Codex, Copilot CLI and Cursor, checked on 2026-10-28 (macOS). The custom platforms `work` and `hybrid` use whatever the user configures. Each fact carries one of three marks:

- **verified**: run or observed on this machine.
- **documented**: stated on the vendor's official page or in its source repository (the `## Verification log` has the URL).
- **unverified**: not found in official sources. The fallback from the design spec (section 8) applies, and it is written next to the fact.

Codex, Copilot CLI and Cursor were not installed here, so nothing about them is **verified**. Their entries are **documented** at best.

## Detecting the platform

Order: the `SHARRON_PLATFORM` environment variable, then the `platform` key in the config, then self-identification (`auto`). `work` and `hybrid` are never detected; they must be set.

| Platform | Signal | Mark |
|---|---|---|
| Claude Code | `CLAUDECODE=1` in every shell command the Bash tool starts. | verified, documented |
| Claude Code | `CLAUDE_CODE_SESSION_ID` holds the current session id in the same shells and in hook commands. It changes on `/clear`, so read it at the moment it is needed instead of caching it. | verified, documented |
| Claude Code | `CLAUDE_CONFIG_DIR` replaces `~/.claude` for settings, session history and plugins. When it is unset the folder is `~/.claude`. | documented |
| Codex | No environment variable is documented. A commit in the Codex source history says `CODEX_THREAD_ID` is injected into the terminal environment, but no official page confirms it. | unverified |
| Copilot CLI | No detection variable is documented. `COPILOT_HOME` moves its config folder and `COPILOT_MODEL` selects the model, but neither says that a session is running. | unverified |
| Cursor | No detection variable is documented. | unverified |

The three unverified platforms are recognised by self-identification: the agent states which product it is running in. Where that is ambiguous, sharron asks the user to set `platform` once.

## Subagents and models

| Platform | How subagents start | Choosing a model per subagent | Mark |
|---|---|---|---|
| Claude Code | The Agent tool. The `model` argument of a call accepts only the aliases `haiku`, `sonnet`, `opus` and `fable`, not full model ids. Without it the agent definition's `model` field applies, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the main conversation's model. | Yes | documented |
| Codex | The user or `AGENTS.md` asks for subagents in natural language; no tool name is documented. Built-in agents are `default`, `worker` and `explorer`. At most `agents.max_concurrent_threads_per_session` run at once. | Yes: a custom agent file (`~/.codex/agents/*.toml` or `.codex/agents/*.toml`) takes `model` and `model_reasoning_effort`; `[agents]` in `config.toml` takes `default_subagent_model` and `default_subagent_reasoning_effort`; an explicit value in the spawn request wins over the defaults. | documented |
| Copilot CLI | The `task` tool. Custom agents are markdown files with frontmatter (`.github/agents/` in a repository, or the user profile). `list_agents`, `read_agent` and `write_agent` manage running agents. | Yes: the agent's `model`, `models` and `reasoningEffort` frontmatter fields, or an explicit per-call value, or the `subagents` override in `~/.copilot/settings.json`. When the session model is `auto`, subagents inherit it. | documented |
| Cursor | The Task tool. Subagents are markdown files in `.cursor/agents/` or `~/.cursor/agents/` (`.claude/agents/` and `.codex/agents/` are read too). A subagent started by a subagent cannot start further ones. | Yes: the `model` frontmatter field takes `inherit` (the default) or a model id. | documented |

The exact tool names for Codex and Cursor are **unverified**. sharron asks for subagents in plain language on those two platforms and does not depend on a tool name.

**Model mapping.** `config.example.toml` ships `[platforms.claude-code.models]` (`haiku`, `sonnet`, `opus`) and `[platforms.copilot.models]` (the Copilot model ids `claude-haiku-5.5`, `claude-sonnet-5.5`, `claude-opus-5.5`, which differ from the API ids in spelling and depend on the user's plan). Codex and Cursor can choose a model per subagent too, but their current model ids were not verified, so no section ships. A user who wants tiers there adds `[platforms.codex.models]` or `[platforms.cursor.models]` to `config.toml`. Until then sharron lets those subagents inherit the parent's model and records the cost as unknown.

**If a platform has no way to start a subagent** (none of the four is in that case today), sharron does the units itself, one after another.

Claude Code allows up to 20 concurrent subagents by default (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`); sharron's own `max_parallel_subagents` stays the lower limit.

## Where writes land

sharron writes `ledger/costs.md`, `registry.toml`, `security-references.toml` and `config.toml` inside the skill folder, so it matters whether the running skill folder is the repository checkout or a copy.

| Platform | Local-path marketplace | Mark |
|---|---|---|
| Claude Code | `claude plugin marketplace add <path to clone>` records a `directory` source, and `claude plugin list --json` shows `readFromFolder` pointing at the clone: the plugin is loaded in place. A copy also lands in the plugin cache (`<config dir>/plugins/cache/<marketplace>/<plugin>/<version>/`) and `installPath` points there, but the folder that is read is the clone. | verified |
| Claude Code | Installed from GitHub (`owner/repo`), the plugin is a cached copy: writes are lost on update. | documented |
| Codex | Installed plugins live in `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`; for a local path the version is `local`, and the host loads from the cache, not from the marketplace entry. Treat it as a copy. | documented |
| Copilot CLI | "Path-sourced plugins in a local (directory-source) marketplace load live from their real directory": editing one takes effect on `/restart` or in a new session. Scope: plugins whose `source` is a path inside a marketplace added from a local path. A plugin installed from GitHub or another remote source is a copy under `~/.copilot/installed-plugins/<marketplace>/<plugin>`. | documented (not run) |
| Cursor | Local plugins are copied into `~/.cursor/plugins/local/<plugin>`; a symlink works only when it points inside that folder. Treat it as a copy. | documented |

For copies, the data sync (`datasync.py`, which `finance.py` runs) detects that the skill folder is not this repository's clone at `plugins/workflow/skills/sharron/`, returns `not-a-clone` and says so once. A copy inside another project's repository counts as a copy too, and nothing is committed or pushed there. A copy only loses the ledger and the settings, not functionality (spec section 8, item 6).

## Background work

sharron starts `refcheck.py check` in the background at activation (step 0). Where background work is not confirmed, it runs the check at step 11 instead.

| Platform | Background shell command | Mark |
|---|---|---|
| Claude Code | The Bash tool takes `run_in_background`; the session is notified when the command exits. Background subagents also exist. | documented |
| Codex | Background terminals (`/ps` lists them) belong to the `unified_exec` feature, known only from third-party writing; no official page confirms them or says whether they are on by default. Run the check at step 11. | unverified |
| Copilot CLI | Shell sessions can run detached: `list_bash`, `read_bash` and `stop_bash` exist, and Ctrl+X then `b` promotes a running shell command to the background. How the model starts one directly is not documented. Run the check at step 11. | documented (partly) |
| Cursor | Subagents can run in the background (`is_background: true`). A background shell command is not documented. Run the check at step 11. | unverified |

## Measuring usage

| Platform | Source of token counts | Mark |
|---|---|---|
| Claude Code | The session transcript: `<config dir>/projects/<cwd with every non-alphanumeric character replaced by "-">/<session id>.jsonl`, where `<config dir>` is `$CLAUDE_CONFIG_DIR` or `~/.claude`. | verified (layout), documented (`CLAUDE_CONFIG_DIR`) |
| Claude Code | Subagent transcripts: `<session id>/subagents/agent-<agent id>.jsonl`, each with a `.meta.json` holding `agentType` and `model`. The agent id the Agent tool returns when a subagent finishes is the id in that file name. | verified (layout), documented (id) |
| Claude Code | Assistant lines repeat once per content block with the same `message.id`, `requestId` and `usage`; count each `requestId` once. | verified |
| Claude Code | `CLAUDE_CODE_PROJECT_DIR_NAME`, set together with `CLAUDE_CONFIG_DIR` at launch, replaces the derived folder name under `projects/`. | documented |
| Codex, Copilot CLI, Cursor | No transcript format was verified. Rows are written with cost `unknown` and the platform recorded. | unverified |

If a subagent's id turns out not to match a transcript file name, maintenance rows are recorded with unknown cost (`--agents unknown --models <tiers>`).

Prices are in `config.example.toml` under `[prices]` and are edited there or overridden in `config.toml`.

## Installing skills

Task 11 uses only the commands in this section. `<owner>/<repo>` is a GitHub repository; `<sha>` is the 40-character commit pinned in the registry; `<plugin>` and `<marketplace>` are names from the repository's `marketplace.json`.

### Skills from this repository (`ref = "self"`)

Add the marketplace once (path form on the main machine, so the ledger stays in the repository; GitHub form elsewhere), then install the plugin:

| Platform | Add the marketplace | Install the plugin | Mark |
|---|---|---|---|
| Claude Code | `claude plugin marketplace add <path to clone>` or `claude plugin marketplace add <owner>/<repo>` | `claude plugin install <plugin>@<marketplace>` | verified |
| Codex | `codex plugin marketplace add <path to clone>` or `codex plugin marketplace add <owner>/<repo>` | `codex plugin add <plugin>@<marketplace>` (the marketplace-add half is documented; the install half comes from the Codex source, not from a run) | documented (marketplace add); documented (source code, not run) (plugin add) |
| Copilot CLI | `copilot plugin marketplace add <path to clone>` or `copilot plugin marketplace add <owner>/<repo>` | `copilot plugin install <plugin>@<marketplace>` | documented |
| Cursor | No command line is documented. Documented: in Customize, find the plugin, choose Install, and pick project or user scope; and Customize, "From GitHub Repository" (the repository needs a `.cursor-plugin/marketplace.json`) on https://cursor.com/docs/skills. Team marketplaces use Dashboard, Plugins & MCPs, "Import from Repo" (Teams or Enterprise). Which of these adds this repository for a single user is not stated. | Install in Customize | documented (Install); unverified (adding a repository as a single user) |

For Cursor, sharron does not install automatically: it tells the user the steps above and passes the `SKILL.md` path to the subagent (spec section 8, item 3).

### Pinned skills from other repositories (`ref` is a commit SHA)

**Marketplace forms** (a repository that is a marketplace, pinned to the commit):

| Platform | Form | Mark |
|---|---|---|
| Claude Code | **Not available.** `claude plugin marketplace add <owner>/<repo>#<sha>` fails with `Remote branch <sha> not found in upstream origin`, and `@<sha>` fails the same way, because the ref is cloned as a branch or tag. `#<branch or tag>` works. Use the skill-folder form below. | verified |
| Codex | `codex plugin marketplace add <owner>/<repo> --ref <sha>`, then `codex plugin add <plugin>@<marketplace>`. The source clones the repository and then runs `git checkout <ref>`, so a SHA works; the command itself was not run. | documented (source code) |
| Copilot CLI | `copilot plugin marketplace add <owner>/<repo>#<ref>` is documented for branches and tags. A SHA there is not documented. Use the skill-folder form. | unverified |
| Cursor | No pinning. Use the skill-folder form. | documented |

**Skill-folder form** (works on every platform, pins exactly, no marketplace needed). Clone into a temporary folder, check out the SHA, copy the skill folder into the personal skills folder, and remove the clone:

```
git clone --quiet https://github.com/<owner>/<repo>.git <temp dir>/src
git -C <temp dir>/src checkout --quiet <sha>
mkdir -p <skills dir>
cp -R <temp dir>/src/<path to skill folder> <skills dir>/<skill>
rm -rf <temp dir>
```

The commands in `registry.toml` do this in one line: they fetch only the one folder (a blobless clone, then `checkout <sha> -- <path>`), refuse when the destination already exists, and pass `-c maintenance.auto=false` to git, because the blob fetch otherwise starts a detached `git maintenance` that writes into the clone while it is being removed. They create the temporary folder as `mktemp -d "${TMPDIR:-/tmp}/sharron.XXXXXX"`, because macOS `mktemp -d` without a template ignores `TMPDIR`.

| Platform | `<skills dir>` (personal skills folder) | Mark |
|---|---|---|
| Claude Code | `~/.claude/skills` | documented |
| Codex | `~/.agents/skills` | documented |
| Copilot CLI | `~/.copilot/skills` (or `~/.agents/skills`) | documented |
| Cursor | `~/.cursor/skills` (or `~/.agents/skills`) | documented |

Copilot CLI also documents `copilot skill add <FILE | URL | DIRECTORY>` for adding one skill, but it takes no pin, so it is not used for pinned installs.

The skill folder must contain `SKILL.md` and its `name` must equal the folder name. A skill that is only part of a plugin that needs hooks or MCP servers cannot be installed this way; the registry entry then needs a marketplace form, or no command (spec section 8, item 10).

### Does a running session see the new skill?

| Platform | Skill folder | Plugin | Mark |
|---|---|---|---|
| Claude Code | Yes: a skill added to or removed from `~/.claude/skills/` is picked up in the running session (live change detection). | `/reload-plugins` in the session, or a new session. | documented |
| Codex | Yes: new and changed skills are detected automatically; restart Codex if one does not appear. | Start a new session. | documented |
| Copilot CLI | `/skills reload`, then `/skills info <skill>` to confirm. | Not documented; start a new session. | documented / unverified |
| Cursor | Skills are discovered when Cursor starts; mid-session pickup is not documented. Start a new chat or restart. | Not documented; restart. | unverified |

When the skill is not visible yet, sharron passes the path of its `SKILL.md` to the subagent instead (spec section 8, item 3), and tells the user once that a restart makes it a normal skill.

## Tool restrictions

sharron keeps tool lists as brief rules for the subagent (spec section 8, item 9). These are the platform controls that exist, for a later decision to enforce them:

| Platform | Control | Mark |
|---|---|---|
| Claude Code | Agent definition frontmatter `tools` (allowlist) and `disallowedTools` (denylist), in `agents/*.md` of a plugin. Plugin agents ignore the `hooks`, `mcpServers` and `permissionMode` fields. Subagents never get `AskUserQuestion`, `ExitPlanMode` and a few others. A plugin with no `agents/` folder has no restriction beyond the brief. | documented |
| Codex | No tool allowlist. A custom agent can switch capabilities off with `features.shell_tool`, `features.apps`, `features.plugins`, `features.memories` and `features.request_permissions_tool`, and can disable skills with `skills.config`. It cannot change `sandbox_mode`, `approval_policy`, `model_provider` or `mcp_servers`. | documented |
| Copilot CLI | The `tools` frontmatter list of a custom agent (default `["*"]`), plus `--available-tools` and `--excluded-tools` on the command line. | documented |
| Cursor | Only `readonly: true` (no file edits and no state-changing shell commands). There is no per-tool allowlist. | documented |

## Verification log

Official sources read on 2026-10-28. "Run" means executed on this machine with `CLAUDE_CONFIG_DIR` set to a throwaway folder (deleted afterwards).

| # | Item | Result | Source or experiment | Date |
|---|---|---|---|---|
| 1 | Claude Code sets `CLAUDECODE` and `CLAUDE_CODE_SESSION_ID` | Both set in Bash tool shells; the session id is updated on `/clear` | https://code.claude.com/docs/en/env-vars ; observed in this session's shell | 2026-10-28 |
| 2 | `CLAUDE_CONFIG_DIR` relocates `~/.claude` | Yes: "All settings, session history, and plugins are stored under this path" | https://code.claude.com/docs/en/env-vars | 2026-10-28 |
| 3 | Transcript path, subagent transcripts, repeated assistant lines | As in `## Measuring usage` | Checked while planning; agent id naming from https://code.claude.com/docs/en/sub-agents | 2026-10-28 |
| 4 | Claude Code per-subagent model and tool restrictions | Aliases only on the Agent tool; `tools` and `disallowedTools` in agent files | https://code.claude.com/docs/en/sub-agents | 2026-10-28 |
| 5 | Claude Code marketplace add forms | `owner/repo[#ref or @ref]`, git URLs, local directories (read in place) | https://code.claude.com/docs/en/plugins/cli-reference | 2026-10-28 |
| 6 | Claude Code marketplace add pinned to a commit SHA | Fails: `Remote branch <sha> not found in upstream origin`, for both `#<sha>` and `@<sha>`. `#main` works | Run: `claude plugin marketplace add <owner>/<repo>#<sha>` and `...#main` | 2026-10-28 |
| 7 | Claude Code local-path marketplace loads in place | `known_marketplaces.json` has a `directory` source; `claude plugin list --json` shows `readFromFolder` as the clone, with a cache copy beside it | Run: add a clone checked out at a SHA, then `claude plugin install <plugin>@<marketplace>` | 2026-10-28 |
| 8 | Claude Code picks up new skills in a running session | Personal skill folders: yes. Plugins: `/reload-plugins` | https://code.claude.com/docs/en/skills ; https://code.claude.com/docs/en/plugins/install | 2026-10-28 |
| 9 | Claude Code background commands | `run_in_background: true` on the Bash tool (also present in this session's tool schema); background subagents | https://code.claude.com/docs/en/tools-reference ; https://code.claude.com/docs/en/sub-agents (background subagents) | 2026-10-28 |
| 10 | Codex subagents, per-agent model, restrictions | `model` and `model_reasoning_effort` in custom agent files; no tool allowlist | https://learn.chatgpt.com/docs/agent-configuration/subagents (redirect of https://developers.openai.com/codex/subagents) | 2026-10-28 |
| 11 | Codex skills folders and pickup | `$HOME/.agents/skills`, `.agents/skills`; detected automatically | https://learn.chatgpt.com/docs/build-skills (redirect of https://developers.openai.com/codex/skills) | 2026-10-28 |
| 12 | Codex plugin install, cache, local path | `codex plugin marketplace add` forms and `--ref`; plugin cache under `~/.codex/plugins/cache/`; local plugins load from the cache | https://developers.openai.com/plugins/build/plugins ; https://learn.chatgpt.com/docs/plugins | 2026-10-28 |
| 13 | Codex marketplace add pinned to a SHA; `codex plugin add` | Source clones then runs `git checkout <ref>`; `codex plugin add <plugin>@<marketplace>` exists. Not run (Codex not installed) | https://github.com/openai/codex : `codex-rs/core-plugins/src/marketplace_add/install.rs`, `codex-rs/cli/src/plugin_cmd.rs` (main branch) | 2026-10-28 |
| 14 | Codex background terminals | Only third-party writing found; unverified | Web search, no official page | 2026-10-28 |
| 15 | Codex detection variable | `CODEX_THREAD_ID` appears only in a commit of the source history; unverified | Web search | 2026-10-28 |
| 16 | Copilot CLI plugin and marketplace commands | `copilot plugin marketplace add`, `copilot plugin install plugin@marketplace`; `owner/repo#ref` for marketplaces; `sha` only inside a plugin source entry | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference ; https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-finding-installing | 2026-10-28 |
| 17 | Copilot CLI custom agents, model, tools; shell tools | Frontmatter `model`, `models`, `reasoningEffort`, `tools`; `task`, `bash`, `read_bash`, `stop_bash` tool names; model list | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference | 2026-10-28 |
| 18 | Copilot CLI skills folders and reload | `~/.copilot/skills`, `~/.agents/skills`; `/skills reload`; `copilot skill add` | https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills ; https://docs.github.com/en/copilot/concepts/agents/about-agent-skills | 2026-10-28 |
| 19 | Copilot CLI local marketplace in place | Documented: path-sourced plugins in a directory-source marketplace "load live from their real directory"; remote installs are copies under `~/.copilot/installed-plugins/`. Not run | https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference | 2026-10-28 |
| 20 | Cursor subagents: model, `readonly`, background | `model` (`inherit` or id), `readonly`, `is_background` | https://cursor.com/docs/subagents | 2026-10-28 |
| 21 | Cursor skills folders and install | `.agents/skills`, `.cursor/skills`, and user-level equivalents; discovered at start; install through plugins only | https://cursor.com/docs/skills | 2026-10-28 |
| 22 | Cursor plugins and local loading | UI only, no command line documented; Install in Customize with project or user scope; team marketplaces via Dashboard, Plugins & MCPs, Import from Repo; local plugins are copied to `~/.cursor/plugins/local`; no commit pinning | https://cursor.com/docs/plugins ; "From GitHub Repository" wording: https://cursor.com/docs/skills | 2026-10-28 |
| 23 | Model prices | Filled in `config.example.toml` | https://platform.claude.com/docs/en/about-claude/pricing (Sonnet 5.5 cache read is 0.10 there; the `claude-api` skill's cached table says 0.20, and the page was used) | 2026-10-28 |
| 24 | Copilot model ids | `claude-haiku-5.5`, `claude-sonnet-5.5`, `claude-opus-5.5` | cli-command-reference page above | 2026-10-28 |
| 25 | Agent id returned by the Agent tool equals the `agent-<id>` file name | Documented; not exercised from a subagent run here | https://code.claude.com/docs/en/sub-agents | 2026-10-28 |
| 26 | Pinned skill-folder install commands, first template, run for real: entry `principle-prove-it-works` (`cursor/plugins` at `99b609a`), all four commands | Each exited 0 and put `SKILL.md` in its skills folder, but two flaws showed. macOS `mktemp -d` ignored `TMPDIR`, so the clone sat in the per-user system temp folder. In 3 of 4 runs `rm -rf "$d"` printed "Directory not empty" and left the clone behind, because the blob fetch during `checkout` starts `git maintenance run --auto --detach` (seen with `GIT_TRACE=1`), which wrote into `.git` during the removal. Template fixed in `registry.toml` (row 27) | Run: each command under `/bin/sh` with `HOME`, `CLAUDE_CONFIG_DIR` and `TMPDIR` set to throwaway folders (deleted afterwards); git 2.54 on macOS | 2026-10-29 |
| 27 | Fixed template (`mktemp -d "${TMPDIR:-/tmp}/sharron.XXXXXX"`, `git -c maintenance.auto=false` on clone and checkout), same entry, all four commands run for real | All four exited 0 and installed one `SKILL.md` each in `<config dir>/skills`, `~/.agents/skills`, `~/.copilot/skills` and `~/.cursor/skills`. The temporary clone was created inside `TMPDIR` and removed; `TMPDIR` was empty afterwards; no `git maintenance` was started | Run as in row 26 | 2026-10-29 |
| 28 | Existing destination: the same four commands run a second time | Each exited 1 at once, created no temporary folder and left the installed files byte-identical (checked with `shasum`) | Run as in row 26 | 2026-10-29 |
