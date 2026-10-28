# sharron user guide

sharron is a way of working packaged as a skill. It plans before it acts, hands work to subagents with clear briefs, has key claims checked by an independent verifier, stops at a decision card before anything risky or irreversible, tracks what each task costs in a ledger, and keeps per-folder memory in `MEMORY.md`. It replies in Traditional Chinese.

This guide is in English like the rest of the repo. When you ask sharron for help, it answers from this file in Traditional Chinese.

Contents:

- [Install](#install)
- [First run](#first-run)
- [Calling sharron](#calling-sharron)
- [The intake and the task card](#the-intake-and-the-task-card)
- [Confirmations and decision cards](#confirmations-and-decision-cards)
- [Memory](#memory)
- [Talking to sharron about settings](#talking-to-sharron-about-settings)
- [Settings and files you can edit](#settings-and-files-you-can-edit)
- [Manual commands](#manual-commands)
- [Troubleshooting](#troubleshooting)

In this guide `<skill>` is the folder `plugins/workflow/skills/sharron` and `<repo>` is your clone of this repository.

## Install

Install `workflow` from your local clone on the machine where you work most, so the cost ledger and your settings stay in the repository and sharron can commit them there.

```bash
claude plugin marketplace add <path to your clone>
claude plugin install workflow@skill-operator
claude plugin install research@skill-operator
```

`research` holds `research-method` and `verify-evidence`, which sharron gives to its researchers and verifiers. The commands above are for Claude Code. Codex and Copilot CLI use the same shape (`codex plugin marketplace add …` then `codex plugin add workflow@skill-operator`, and `copilot plugin marketplace add …` then `copilot plugin install workflow@skill-operator`); see [`references/platforms.md`](references/platforms.md#installing-skills) for the checked facts and their marks. Cursor has no command-line install: use Customize, find the plugin and choose Install.

On every other machine or platform, install the plugin from GitHub with the table in the repository [README](../../../../README.md#install). Those installs are copies: they work in full, but they lose only two things, the ledger and your settings, because the copy is replaced when the plugin updates and is not a git clone. sharron notices this and tells you once (`not-a-clone`). See [Where writes land](references/platforms.md#where-writes-land).

sharron's scripts need Python 3.11 or newer and git. You do not have to pick the interpreter: `scripts/run.sh` looks for `python3.14` down to `python3.11`, then `python3`, then `uv`, and says what to install when none fits.

Registry skills that sharron installs for you (the service list) come from `registry.toml`. Claude Code cannot pin a marketplace to a commit SHA, so a pinned skill from another repository is copied into your personal skills folder at exactly the pinned commit. Cursor never gets automatic installs: sharron tells you the steps instead. Details: [`references/registry.md`](references/registry.md#installing-a-missing-skill).

## First run

Nothing needs setting up. On the first task sharron creates and changes only this:

- `MEMORY.md` at the root of your workspace (the top of the git work tree, or the current folder when there is no repository), with the skeleton from [`references/memory.md`](references/memory.md#format). If the file already exists without sharron's marker, sharron keeps your text and appends its sections below.
- In a git repository, sharron first makes git ignore `MEMORY.md` by adding `/MEMORY.md` to `.git/info/exclude`. That file is local to your clone and is never committed. sharron tells you so once (`excluded`).
- `config.toml` next to `config.example.toml`, only when you first change a setting. It holds only the keys you changed. It is gitignored.
- `state/` in the skill folder (reference-check times, traces, update proposals). It is gitignored.

Questions like "what is 3 × 17" or a settings change leave no `MEMORY.md` entry and no ledger row.

## Calling sharron

Say her name at the start of the request, in any capitalization, or run `/workflow:sharron`. Without the name, ordinary requests do not trigger her, and a sentence like "email Sharron the report" is not a call.

One example per playbook:

| Playbook | Example | What happens |
|---|---|---|
| `simple-answer` | 「sharron，台北到高雄高鐵大概多久？」 | A direct answer with a label on the important claim. No subagents, no memory entry. |
| `research` | 「sharron，幫我查三家主要的日本 eSIM 方案，比較價格和涵蓋範圍」 | Researchers collect sources in parallel, a verifier re-reads the most important claims, and you get a labeled summary with links. |
| `planning` | 「sharron，幫我排 5 天的京都行程，預算 6 萬」 | A plan with options, buffers and checks. Nothing is booked or sent. |
| `action` | 「sharron，寄一封信給房東說下個月不續約」 | A plan first, a decision card before anything leaves your machine, and an exact read-back of what was done. |
| `decision-support` | 「sharron，我該買 A 還是 B 筆電？比較一下」 | Criteria and weights, facts per option, a comparison with a sensitivity check. You decide. |
| `learning` | 「sharron，教我 Git rebase，一次一個觀念」 | One concept at a time with a check of your understanding; progress goes into `MEMORY.md`. |
| `coding` | 「sharron，寫一個把 CSV 轉成 JSON 的 Python 腳本，要有測試」 | One engineer works in your folder following the project's own conventions; a reviewer checks the diff; nothing is deployed unless you ask. |
| `settings-help` | 「sharron 怎麼用」「sharron 顯示設定」 | Answers from this guide or changes a setting; see [Talking to sharron about settings](#talking-to-sharron-about-settings). |
| `custom` | 「sharron，我要做一個每週整理待辦的流程」 | When nothing fits, she designs a playbook first, tells you what it is for and how each step is checked, then runs it. |

Background reference updates (`maintenance`) are started by sharron herself, never by a request.

## The intake and the task card

For anything beyond a trivial request, sharron drafts what she thinks you want from your words, `MEMORY.md`, the workspace and the defaults, and marks each part known, assumed or unknown. She asks only what would change the plan: at most 3 questions, usually in one round, each with 2 to 4 options and a recommended default.

Answer quickly with 「照預設」 to take every recommended default. Difficulty 1 to 2 tasks and background runs ask nothing; the reply states the assumptions instead. For actions she always asks what she may do (authority) unless you already said. An answer you give that holds for later tasks is remembered as a preference marked 〔你說的〕.

Then she shows the task card:

```
任務卡
- 目標：…
- 完成條件：…
- 用途：…
- 限制：期限 …／預算約 US$…（帳本建議）／不碰 …
- 授權：只查資料／草稿／可逆的部分直接執行
- 深度：完整版（難度 3，預計派 2 個 subagent）
- 假設：…（沒問你、先這樣假設的部分）
```

Read 完成條件 (when she will call it done), 授權 (what she may do without asking) and 假設 (what she guessed). Correct any of them before she starts. The budget is in equivalent USD and states its basis: `p80` of past similar tasks, a `regression`, or the `default` from the config until the ledger has data. For difficulty 4 to 5 the card is also the plan confirmation: reply 「好」 to go ahead, or say what to change. More: [`references/intake.md`](references/intake.md).

## Confirmations and decision cards

Two separate scales are in play, so do not mix them up:

- **R0 to R4** rates an action by how reversible it is, who is affected, money, privacy and commitment. The highest dimension wins, and when unsure sharron uses R3.
- **L0 to L4** says who decides. R0 reading is L0; an R1 or R2 action is L2 (she decides and summarizes it at the end of the reply); R3 needs your L3 confirmation; R4 needs an L4 decision card.

Details and the full table: [`references/decisions-and-risk.md`](references/decisions-and-risk.md).

**L3 is a one-line confirmation.** sharron has the plan reviewed by a subagent that did not make it, then asks:

```
需要你確認：<要做的事，含對象與金額／數量>（原因：<一句話>）。要執行嗎？（回「好」或說明要改的地方）
```

Reply 「好」 to go ahead, or say what to change. Only a yes lets her act. L3 covers R3 actions, a budget overrun, more than 5 subagents or parallel T3 subagents, a difficulty 4 to 5 plan, loosening a safeguard (deleting a standing order, turning off auto install) and running the evals.

**L4 is a decision card** (決策卡), for R4 actions, life-direction choices, large-impact ambiguity, an important disagreement between sharron and the reviewer, and untracking `MEMORY.md`. It has a background, the options, a recommendation with the reason, the risk and cost of each option and whether it can be undone, a deadline and the basis. Answer by naming an option (「選 A」), or say what you want instead. Nothing happens until you answer.

There are no timeouts. An unanswered L3 or L4 waits: the task is marked 等待 in `MEMORY.md` with a checkpoint, and the next task offers to resume it.

Standing orders (`standing_orders.always` and `.never` in `config.toml`) are your permanent rules. An `always` rule goes into every plan. A `never` rule is Forbidden: sharron refuses and does not split the action into smaller steps; she asks you to remove the rule first, and that removal is an L3 confirmation.

## Memory

`MEMORY.md` lives at the workspace root. It holds your preferences and lessons, and one entry per task: goal, done-when, decisions with their level and reason (`- 決策：L2 — …（依據：…）`), checkpoints and results. Each preference or lesson ends with a marker for where it came from: 〔你說的〕 (you said it), 〔已驗證〕 (verified, with the source) or 〔推論〕 (sharron inferred it and will re-check before relying on it). Text from web pages or emails is never stored as an instruction, and secrets are never stored.

- **To correct or remove an entry**, say so ("sharron，把那條偏好刪掉" or "那條不對，改成…") or edit the file yourself. It is a plain Markdown file in your workspace.
- **To see paused tasks**, say 「sharron 有哪些暫停的任務」. Every new task also lists them first.
- **It is never committed.** `MEMORY.md` can hold personal context, so `memory_guard.py` makes git ignore it and checks before any commit or push that it is not staged or outgoing. If it is already tracked, sharron will not write to it and asks you with a decision card; see [Troubleshooting](#troubleshooting). She never runs `git add -f MEMORY.md`. This repository's own `.gitignore` also lists it.
- **It stays short.** Past about 200 lines she compresses the oldest finished tasks, never preferences.
- After every 20 ledger rows (or when you ask), sharron reads the traces of failed, partial and corrected tasks and writes proposed fixes under 偏好與教訓 for you to accept. She does not change the skill herself.

Format and rules: [`references/memory.md`](references/memory.md).

## Talking to sharron about settings

The `settings-help` playbook has no intake, no memory entry and no ledger row.

| You say (examples) | sharron does | Level |
|---|---|---|
| 「sharron 怎麼用」「sharron help」 | Summarizes `GUIDE.md` | L0 |
| 「sharron 顯示設定」 | Runs `config.py show` and lists the effective settings with their sources | L0 |
| 「sharron 把 reviewer 改成 T3」「把 work 平台的模型設成 X」 | Edits `config.toml` (creating it from the example if needed), runs `config.py validate`, shows the diff | L2 |
| 「sharron 加一條常備命令：絕不……」 | Adds it to `config.toml` | L2 |
| 「sharron 刪掉常備命令……」「關掉自動安裝」 | Changes it after a one-line confirmation, because it loosens a safeguard | L3 |
| 「sharron 把 <skill> 加進註冊表」 | Adds the entry you describe (repo, `ref`, install commands, roles), shows the diff, syncs `registry.toml` | L2 |
| 「sharron 改一下 engineer 的角色提示」 | Edits `roles/engineer.md` (or `.local.md` for this machine only) and shows the diff; leaves committing to you | L2 |
| 「sharron 預算狀況」 | Summarizes recent spend and the budget suggestion per playbook and difficulty | L0 |
| 「sharron 有哪些暫停的任務」 | Lists paused and waiting tasks from `MEMORY.md` | L0 |
| 「sharron 現在更新資安參考清單」 | Runs the reference check now, ignoring the interval | L2 |
| 「sharron 跑評測」 | Runs the eval set after a one-line confirmation, because it costs quota | L3 |

When sharron changes a setting she writes only that key, runs `config.py validate`, and undoes the change and shows the allowed values if validation fails. The steps are in [`references/playbooks.md`](references/playbooks.md#settings-and-help).

## Settings and files you can edit

### Settings reference

`config.toml` sits next to `config.example.toml` and is gitignored. Put in it only the keys you want to change; every other key keeps the default from the example, so later default updates (new prices, for example) still reach you. `SHARRON_PLATFORM` in the environment overrides `platform`.

| Key | Default | Allowed values | Effect |
|---|---|---|---|
| `platform` | `auto` | `auto`, `claude-code`, `codex`, `copilot`, `cursor`, `work`, `hybrid` | Which platform's model mapping applies. `work` and `hybrid` must be set explicitly; the `SHARRON_PLATFORM` environment variable overrides this key |
| `auto_install` | `true` | `true`, `false` | Install missing registry skills automatically |
| `max_parallel_subagents` | `3` | 1–10 | How many subagents may run at once |
| `max_skills_per_brief` | `4` | 1–10 | At most this many service-list skills per brief; the most specific win |
| `platforms.<platform>.models.T1` / `T2` / `T3` | claude-code: `haiku` / `sonnet` / `opus`; copilot: `claude-haiku-5.5` / `claude-sonnet-5.5` / `claude-opus-5.5`; `work`, `hybrid`: empty | Model IDs | The model each tier uses on that platform; on `work`, put the same model in all three |
| `platforms.hybrid.available` | `[]` | List of model IDs | The models you can choose from on `hybrid` |
| `roles.<role>` | See [`budget-and-models.md`](references/budget-and-models.md#tiers) | `T1`, `T2`, `T3` | Default tier per role; rules such as "T3 for R3 and above" can still raise it |
| `prices."<model>"` | The models listed in `config.example.toml` | `input`, `output`, `cache_write`, `cache_read` in USD per million tokens | Converting measured tokens into equivalent USD |
| `risk.currency`, `risk.small_amount`, `risk.large_amount` | `TWD`, `500`, `3000` | Currency code, numbers | The money thresholds behind R2, R3 and R4 |
| `budget.default_per_task` | `0.2`, `0.5`, `1.5`, `4.0`, `10.0` (difficulty 1–5) | USD | Budgets used until the ledger has enough data |
| `budget.overrun_factor` | `1.5` | Greater than 1 | Measured spend above suggestion × factor pauses the task and asks |
| `standing_orders.always`, `standing_orders.never` | `[]` | Lists of plain sentences | Applied to every plan / forbidden outright |
| `installed.<skill>` | Written by sharron | — | Record of automatic installs; not edited by hand |

Three notes. A model with no entry in `prices` is recorded as `unknown` cost, never as 0; add a `prices."<model>"` table for it. Codex and Cursor ship no model mapping; add `[platforms.codex.models]` or `[platforms.cursor.models]` if you want tiers there. After any edit, run `config.py validate` (see [Manual commands](#manual-commands)).

### Other files

All paths are inside `<skill>`.

| File | Who edits it | How |
|---|---|---|
| `config.toml` | You, or sharron when you ask | Local only, gitignored. Only changed keys. |
| `config.example.toml` | You, by hand | The defaults. Committed. |
| `registry.toml` | You, by hand, or sharron when you ask | The skills sharron may give to subagents and the scanner tools. An entry has `name`, `repo`, `plugin`, `status`, `roles`, `playbooks`, `domains`, `tags` (coding skills), `min_tier`, `ref` and one install command per platform in `[skills.install]`. `ref = "self"` marks a skill from this repo; every other entry pins a 40-character commit SHA, and each install command must contain it. A newer upstream version arrives only when you change `ref`. Format: [`references/registry.md`](references/registry.md#registry-format). |
| `security-references.toml` | You add sources by hand; `refcheck.py` updates editions | You add or remove a `[[sources]]` entry (`id`, `name`, `kind`, `edition`, `status`, `url`, `official_domains`, `applies_to`, `items`, `check_every_days`, `probe`) in the layout described at the top of the file. The automatic update may change only `edition`, `status`, `url`, `items` and `probe` of an existing source, only after a verifier confirmed it against the official page, and it appends a `[[changelog]]` entry. |
| `roles/<role>.md` | You | The role prompts. Committed, so edits affect everyone using your clone. |
| `roles/<role>.local.md` | You | The same, for this machine only. Gitignored; sharron appends it after the role prompt. Do not put absolute home paths in it (see [Troubleshooting](#troubleshooting)). |
| `ledger/costs.md` | `finance.py` only | Append-only cost ledger. Never edit it by hand. |
| `state/` | Scripts | Reference-check times, redacted traces, update proposals. Local only. |
| `evals/` | You | Eval cases and fixtures for checking the skill on each platform. Running them costs quota, so it is always manual. |

When you ask sharron to add a registry entry, she checks that `registry.toml` has no uncommitted change of yours first, makes the edit, validates the file with `detect_stack.py select`, shows you the diff, then commits and pushes just that file with `datasync.py sync registry.toml`. The steps: [`references/registry.md`](references/registry.md#editing-the-registry).

## Manual commands

Run each from the root of your clone (or any workspace, with the path to `<skill>` adjusted). Scripts print one JSON object on stdout; `config.py` prints text lines. One line on stderr means bad input. Every script accepts `--help`.

```bash
# Settings
sh plugins/workflow/skills/sharron/scripts/run.sh config.py show
sh plugins/workflow/skills/sharron/scripts/run.sh config.py validate

# Memory safety (run in the workspace)
sh plugins/workflow/skills/sharron/scripts/run.sh memory_guard.py check
sh plugins/workflow/skills/sharron/scripts/run.sh memory_guard.py precommit

# Budget and ledger
sh plugins/workflow/skills/sharron/scripts/run.sh finance.py suggest --platform claude-code --playbook research --difficulty 3
sh plugins/workflow/skills/sharron/scripts/run.sh finance.py usage --platform claude-code --since 2026-10-28T09:00:00+08:00 --budget 1.5
sh plugins/workflow/skills/sharron/scripts/run.sh finance.py record --platform claude-code --task-id t-20261028-01 --since 2026-10-28T09:00:00+08:00 --playbook research --domain travel --difficulty 3 --subagents 2 --outcome done --verified 3/3
sh plugins/workflow/skills/sharron/scripts/run.sh finance.py correct --task-id t-20261028-01

# Security references
sh plugins/workflow/skills/sharron/scripts/run.sh refcheck.py check
sh plugins/workflow/skills/sharron/scripts/run.sh refcheck.py check --force
sh plugins/workflow/skills/sharron/scripts/run.sh refcheck.py apply plugins/workflow/skills/sharron/state/update-<source id>.json
sh plugins/workflow/skills/sharron/scripts/run.sh refcheck.py apply --no-change --source <source id>

# Skill selection and stack detection
sh plugins/workflow/skills/sharron/scripts/run.sh detect_stack.py tags --workspace <folder>
sh plugins/workflow/skills/sharron/scripts/run.sh detect_stack.py select --role engineer --playbook coding --domain coding --tier T2

# Data sync (repeat a commit and push of one data file)
sh plugins/workflow/skills/sharron/scripts/run.sh datasync.py sync registry.toml --message "chore(sharron): update registry [skip ci]"

# Traces
sh plugins/workflow/skills/sharron/scripts/run.sh trace.py prune
```

Notes on the less obvious ones:

- `finance.py suggest` prints `{"budget_usd", "method", "n"}`. `--since` is the ISO start time of the task, with its offset. `record` and `correct` also commit and push the ledger row for you; `correct` is for when a finished task's result turned out wrong, and removes it from the budget suggestions. `finance.py record` also takes `--agents` / `--exclude-agents` to limit which subagent transcripts are measured. See [`references/finance.md`](references/finance.md).
- `refcheck.py check` probes only the sources that are due (7 days, 1 day for beta sources); `--force` ignores that. It never changes the list. `apply` is for a verified update file written by sharron; a bad file exits 1 and writes nothing. The full procedure: [`references/security-review.md`](references/security-review.md#background-reference-updates).
- `datasync.py sync` takes one of `ledger/costs.md`, `security-references.toml` or `registry.toml`, relative to the skill folder, and a message that starts with `chore(sharron): ` and contains `[skip ci]`. The messages for each file are in the table in [`references/finance.md`](references/finance.md#data-sync). It commits whatever diff the file has, so check `git diff` first.
- `detect_stack.py select` also exits 1 with one line when `registry.toml` is invalid, which is how a registry edit is validated.
- `trace.py prune` deletes traces beyond the newest 50 or older than 30 days; starting a new trace already does this.

## Troubleshooting

**sharron does not trigger.** She starts only when you address her by name ("sharron, …", in any capitalization), ask for the Sharron way, or run `/workflow:sharron`. A request that does not mention her never triggers her, even about research or coding. If the name is there and nothing happens, the plugin is probably not loaded: check that `workflow@skill-operator` is installed, and start a new session or run `/reload-plugins`, because a running session may not see a new plugin ([`references/platforms.md`](references/platforms.md#does-a-running-session-see-the-new-skill)).

**Ledger rows are not committed.** The reply says why. Run `git status` in your clone and match the reason:

- A **cache copy** (`not-a-clone`): the plugin was installed from GitHub or copied into a plugin cache, so the row only exists in that copy and is lost on update. Install from your local clone ([Install](#install)) if you want the ledger in the repo.
- **`commit-failed`**: the commit did not go through. Either the repository's pre-commit check failed, or a rebase, merge, cherry-pick, revert or bisect is in progress, or HEAD is detached. The row is already written to `ledger/costs.md` and the next `finance.py record` commits it together with its own row. sharron never bypasses the check (`--no-verify`). The pre-commit hook rebuilds the generated manifests and the README catalog, so it can fail while other changes in the clone are in progress and the regenerated files are not staged: run `make build`, then commit or stash that other work, and the next ledger commit goes through.
- A path with a home directory in a role file: do not put absolute home paths (`/Users/<you>/…`) in `roles/*.local.md` or anywhere else in the skill folder. `make check` and the pre-commit hook scan the skill folder for them, and the failure blocks the ledger commit.

**A push was skipped.** The row or file is committed locally and pushed later. `reason` tells you why; the reply line says it in Chinese. sharron pushes only from `main`, with an upstream set, and only when every outgoing commit is a sharron data commit touching nothing but `ledger/costs.md`, `security-references.toml` or `registry.toml`. She never force-pushes.

| `reason` | Meaning | What to do |
|---|---|---|
| `not-a-clone` | The skill folder is not inside a git work tree (a plugin cache copy). Said once. | Install from your local clone. |
| `commit-failed` | The commit failed or an operation is in progress; `detail` says which. | Finish the rebase or merge, or fix the failing check. For `registry.toml` and `security-references.toml` sharron does not retry the commit: run the `git commit -m "<message>" -- <file>` command her reply gives. |
| `not-on-default-branch` | Committed, but you are not on `main`. | Nothing; it goes out with your next push from `main`. |
| `no-upstream` | The branch has no upstream. | `git push -u origin <branch>`; later syncs push on their own. |
| `fetch-failed` | The remote could not be reached (also after 2 minutes). | Fix the network; the next sync retries. |
| `other-outgoing-commits` | Other unpushed commits exist, which she will not push for you. | Push them yourself; the data commits go along. |
| `remote-ahead-dirty-tree` | The remote has new commits to rebase onto, but your working tree has uncommitted changes. | Commit or stash your changes; the next sync retries. |
| `rebase-conflict` | The rebase onto the remote conflicted (only `ledger/costs.md` is resolved automatically, by keeping both sets of rows). She aborted it. | Resolve and push yourself. |
| `memory-guard` | `MEMORY.md` is staged or in an outgoing commit, so the push was blocked. | See the `MEMORY.md` entry below. |
| `push-failed` | The push itself failed; `detail` has git's message. | Fix the cause (credentials, remote rules); the next sync retries. |

The reply lines and the full retry rules: [`references/finance.md`](references/finance.md#reply-lines).

**`MEMORY.md` is tracked, or git still shows it.** `memory_guard.py check` returns one of four statuses. `ok` and `excluded` need nothing from you (`excluded` means it added `/MEMORY.md` to `.git/info/exclude`). The other two stop sharron writing to the file, and she asks with a decision card; until you answer, memory stays in the conversation.

| `status` | Meaning | Fix |
|---|---|---|
| `tracked` | git already tracks `MEMORY.md`. | `git rm --cached MEMORY.md` keeps your local copy and stages the removal for you to commit. sharron runs it only if you choose that option. |
| `not-ignored` | A `.gitignore` rule re-includes it (find it with `git check-ignore -v MEMORY.md`). | Add a `/MEMORY.md` line to the `.gitignore` at the workspace root, after that rule. |
| `blocked` (from `precommit`) | `MEMORY.md` is staged or in an unpushed commit, so sharron will not commit or push. | `git restore --staged MEMORY.md`. A commit that already holds it is yours to rewrite; sharron does not rewrite history. |

See [`references/memory.md`](references/memory.md#git-safety).

**A reference update failed.** The reply says something like 「資安參考清單檢查失敗（<來源>：<原因>），下次會再試」. A source whose probe failed is simply left alone: its check time is not moved, so the next `refcheck.py check` tries it again. sharron mentions each failing source once per task. If the page really changed but sharron could not verify the update, the change stays pending and is retried on the next activation. If you want to see it now, run `refcheck.py check --force`. Pending changes and proposals: [`references/security-review.md`](references/security-review.md#background-reference-updates).

**sharron says `registry.toml` or `security-references.toml` has an uncommitted change.** Either it is your own edit, or an earlier commit of sharron's failed. sharron will not commit a change she did not make in the current task, and she will not write that file (no registry edit, no reference update) while the diff exists, because the commit that follows would carry your diff too. A pending reference change stays pending. Review it with `git diff -- plugins/workflow/skills/sharron/registry.toml`, then commit it yourself, or discard it, and ask again.

**Registry edits do not take.** `detect_stack.py select` exits 1 with one line when `registry.toml` is invalid (a pinned entry whose install command lacks its SHA, an unknown tag, a bad platform key). sharron restores the previous text and shows you the line. Fix the entry and ask again.

**The numbers look off.** Budgets are in equivalent USD from the prices in `config.toml` and `config.example.toml`; a model with no price is recorded as `unknown`, which does not affect suggestions. If a finished task turned out wrong, tell sharron so it can be marked with `finance.py correct` and leave the suggestions.
