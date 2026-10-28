# Finance

How sharron measures what a task cost, keeps the cost ledger, suggests the next budget, and saves the ledger to the repository. All amounts are equivalent USD (token counts times the prices in the config), not an invoice.

Contents:

- [Measuring usage](#measuring-usage)
- [Ledger](#ledger)
- [Budget suggestions](#budget-suggestions)
- [Data sync](#data-sync)
- [Reply lines](#reply-lines)

`<skill>` is the sharron skill folder. Run every script as `sh <skill>/scripts/run.sh <script>.py …` and never `cd` into the skill folder. Each script prints one JSON object. Bad input prints one line on stderr and exits 1; report that line as it is.

## Measuring usage

Pass `--platform` on every call: when the `platform` setting is `auto`, the script cannot detect it and exits 1.

**Claude Code.** The script reads the session transcript and the subagent transcripts, from the task's start time onward. It reads only `type`, `timestamp`, `requestId`, `message.id`, `message.model` and `message.usage`, never message content. The session comes from `CLAUDE_CODE_SESSION_ID` and the folder from `CLAUDE_CONFIG_DIR` (default `~/.claude`); `--session-id` overrides the first. The paths and the rules for counting are in [`platforms.md`](platforms.md#measuring-usage); they are not repeated here.

```
sh <skill>/scripts/run.sh finance.py usage --platform claude-code --since <task start, ISO time> [--budget <USD>]
sh <skill>/scripts/run.sh finance.py record --platform claude-code --task-id <t-YYYYMMDD-NN> --since <task start, ISO time> \
    --playbook <id> --domain <domain> --difficulty <1-5> --subagents <n> --outcome <done|partial|failed|cancelled> --verified <confirmed>/<checked>
```

- `usage` prints `measurement`, `cost_usd`, `input_tokens`, `output_tokens`, `cache_tokens`, `models`, `unpriced_models` and `note`. With `--budget` it also prints `limit_usd` (budget times `overrun_factor`) and `over_budget`.
- A model with no price in the config makes the cost `unknown` and is named in `unpriced_models`. Tell the user which model needs a price in `[prices]`.
- **Empty usage is recorded as `unknown`, never as a measured 0.** When the transcripts hold nothing since `--since` (a wrong start time or session), `measurement` is `unknown` and `note` says why. Check `--since` and the session before recording.
- `--since` is the start time written in the task's `MEMORY.md` entry. Use the ISO form with the offset, for example `2026-10-28T09:30:00+08:00`.

**Maintenance rows.** The subagents of a background reference update (see [`security-review.md`](security-review.md#background-reference-updates)) are measured on their own, with `--agents <agent ids>` (comma-separated; the id the Agent tool returned when each subagent finished). `--agents` measures only those subagent transcripts and leaves the main transcript out. The row of the task that overlapped the update passes `--exclude-agents <the same ids>`, so the cost is counted once.

```
sh <skill>/scripts/run.sh finance.py record --platform claude-code --task-id <m-YYYYMMDD-NN> --since <update start, ISO time> \
    --playbook maintenance --domain security-references --difficulty 1 --subagents <n> --outcome done --verified <confirmed>/<checked> \
    --agents <agent id>,<agent id>
```

If the agent ids are unknown, pass `--agents unknown --models <tiers>` (for example `T1,T2`). No transcript matches, so the row is recorded with cost `unknown`. Without `--agents` the script would measure the main transcript and bill the whole task to the maintenance row.

**Other platforms.** Codex, Copilot CLI and Cursor have no verified transcript format. Record what the platform reports, as `measured`, by passing the figures it gave:

```
sh <skill>/scripts/run.sh finance.py record --platform <codex|copilot|cursor|work|hybrid> --task-id <id> --since <ISO time> \
    --playbook <id> --domain <domain> --difficulty <1-5> --subagents <n> --outcome <outcome> --verified <c>/<n> \
    [--input-tokens <n>] [--output-tokens <n>] [--cache-tokens <n>] [--cost-usd <USD>] [--models <list>]
```

Any figure left out is stored as `unknown`. When the platform reports nothing, pass none of the four figures: the row is `unknown` with the subagent count and `--models` (the tiers, such as `T1,T2`). `usage` on these platforms prints `unknown`, so the overrun check is skipped and no overrun is claimed.

## Ledger

`ledger/costs.md` in the skill folder. The script writes it; nobody edits it by hand, and past rows are never changed.

- **Summary block** between `<!-- summary:start -->` and `<!-- summary:end -->`: n, median and 80th percentile per platform, playbook and difficulty, generated from the successful rows.
- **Tasks table**, one row per finished task, no task descriptions. Columns: `task_id`, `date`, `platform`, `playbook`, `domain`, `difficulty`, `subagents`, `models`, `input_tokens`, `output_tokens`, `cache_tokens`, `cost_usd`, `outcome`, `verified`, `measurement`.
  - `outcome` is `done`, `partial`, `failed` or `cancelled`.
  - `verified` is claims confirmed over claims checked, such as `3/3`.
  - `measurement` is `measured` or `unknown`. `cache_tokens` is cache writes plus cache reads.
  - `domain` is lowercase words joined by hyphens. Recording the same `task_id` twice is refused.
- **Corrections table**: `task_id`, `date`. When the user says a finished task's result was wrong, run `sh <skill>/scripts/run.sh finance.py correct --task-id <id>`. It appends a row (once per task) and syncs; the task then leaves the summary and the budget suggestions. The task must already be in the ledger.
- Both tables are append-only. The file is written atomically under a lock, so two sessions cannot interleave.
- `simple-answer` and `settings-help` tasks get no row. A `maintenance` row is written only for a background reference update.

### Where writes land

sharron writes to the copy of the skill the platform loaded; see [`platforms.md`](platforms.md#where-writes-land).

- **Loaded in place from the local clone** (Claude Code and Copilot CLI with a marketplace added by local path): the ledger and `config.toml` are in the repository, and the row is committed there.
- **Installed from GitHub, or copied into a plugin cache** (Codex and Cursor always): the row stays in the copy, is lost when the plugin updates and never reaches the repository. The script detects this (the skill folder is not inside a git work tree), returns reason `not-a-clone` with a `notice` once, and sharron passes it on.

## Budget suggestions

```
sh <skill>/scripts/run.sh finance.py suggest --platform <platform> --playbook <id> --difficulty <1-5>
```

It prints `{"budget_usd", "method", "n"}`. Say the basis (method and n) with the amount.

The script uses only successful rows: `measurement` is `measured`, the cost is known, `outcome` is `done`, every checked claim is confirmed (`verified` is `n/n`), and the task has no correction. Cheap but poor runs therefore do not pull budgets down. It counts rows of the same platform and playbook, then picks the first rule that applies:

1. Same difficulty and at least 5 rows: the 80th percentile of their costs (`method` is `p80`).
2. Otherwise at least 10 rows on the playbook: a least-squares fit of cost on difficulty, evaluated at this difficulty and never below the cheapest row (`regression`). It falls back to rule 3 when every row has the same difficulty.
3. Otherwise the config default for this difficulty (`default`, `n` is 0). The defaults are in `[budget]`; read them with `sh <skill>/scripts/run.sh config.py show`.

**Overrun.** After each batch of subagents, run `usage` with `--budget <suggestion>`. When `over_budget` is true (spend above the suggestion times `overrun_factor`, default 1.5), pause non-urgent work and ask whether to continue, as an L3 confirmation. The procedure and the wording are in [`budget-and-models.md`](budget-and-models.md#overrun-check) and [`decisions-and-risk.md`](decisions-and-risk.md#l3-confirmation).

## Data sync

`record` and `correct` append to the ledger and then run the data sync. The same procedure writes `security-references.toml` (after `refcheck.py apply`) and `registry.toml` (after an edit the user asked for). It can also be run on its own, which is how a sync that did not finish is repeated:

```
sh <skill>/scripts/run.sh datasync.py sync <ledger/costs.md|security-references.toml|registry.toml> --message "<commit message>"
```

| File | Commit message |
|---|---|
| `ledger/costs.md` (record) | `chore(sharron): record task cost [skip ci]` |
| `ledger/costs.md` (correct) | `chore(sharron): record task correction [skip ci]` |
| `security-references.toml` | `chore(sharron): update security references [skip ci]` |
| `registry.toml` | `chore(sharron): update registry [skip ci]` |

The script prints `{"committed", "pushed", "reason", "detail", "notice"}`. A `reason` is not an error: the data stays committed, or in the working tree, and the next sync tries again. The decision level is L2.

Safeguards, so nothing else is published by accident:

- Only the three data files are accepted. The message must start with `chore(sharron): ` and contain `[skip ci]`, which keeps data-only pushes from running CI and the release workflow.
- Commits with a pathspec, so only that one file is committed even when other changes are staged. Never uses `--no-verify`: if the repository's pre-commit check fails, the row stays uncommitted (`commit-failed`) and the next sync commits it together with its own row. It does not commit while HEAD is detached or a rebase, merge, cherry-pick, revert or bisect is in progress.
- Pushes only from the default branch, with an upstream set, and only when every outgoing commit is a sharron data commit that touches nothing but the three data files. A fetch or push that takes more than 2 minutes counts as failed.
- When the remote is ahead, it rebases onto it (the working tree must be clean). The ledger is append-only, so a conflict in `ledger/costs.md` is resolved by keeping both sets of rows. Any other conflict aborts the rebase, skips the push and is reported.
- Runs `memory_guard.py precommit` before every push and refuses to push when `MEMORY.md` is staged or in an outgoing commit (see [`memory.md`](memory.md#git-safety)).
- Never force-pushes.

## Reply lines

Say one line, in Traditional Chinese, in the reply (step 10). Pick it from the sync result. For `security-references.toml` write 「資安參考清單」, and for `registry.toml` write 「登錄表」, in place of 「帳本」.

| Result | Line |
|---|---|
| `pushed` is true | 「帳本已自動 commit 並 push」 |
| `reason` is null and `pushed` is false | Nothing to commit or push. Say nothing. |
| `not-a-clone` | 「這份 sharron 不是 git 複本，帳本只留在這裡，不會進到 repo；想保留的話，請從本機的 clone 安裝。」 Say it only when `notice` is not null; the script gives it once. |
| `commit-failed` | 「帳本已寫入檔案，但 commit 沒成功（<detail>）；下次執行時會連同新的一列一起 commit。」 When `detail` names a git operation in progress (a rebase, a merge, a detached HEAD), say so in Chinese and add that the row is committed once the operation ends. |
| `not-on-default-branch` | 「帳本已 commit，但目前不在預設分支，沒有自動 push；會隨你下一次 push 一起送出。」 |
| `no-upstream` | 「帳本已 commit，但這個分支沒有設定上游，沒有自動 push；設好上游（例如 git push -u）後，下次就會自動送出。」 |
| `fetch-failed` | 「帳本已 commit，但連不上遠端（<detail>），沒有 push；網路恢復後下次會再試。」 |
| `other-outgoing-commits` | 「帳本已 commit，但本機還有其他尚未 push 的 commit，為了不把別的內容一起推出去，沒有自動 push；你自己 push 時會一併送出。」 |
| `remote-ahead-dirty-tree` | 「帳本已 commit，但遠端有新的 commit 要先合併，而你的工作目錄還有未提交的修改，沒有 push；整理好修改後，下次會再試。」 |
| `rebase-conflict` | 「帳本已 commit，但和遠端合併時有衝突（<detail>），已取消合併、沒有 push；請你處理完衝突後再 push。」 |
| `memory-guard` | 「帳本已 commit，但 MEMORY.md 在暫存區或待推送的 commit 裡，已擋下 push；請先把它移出去（見 memory.md），再 push。」 |
| `push-failed` | 「帳本已 commit，但 push 沒成功（<detail>）；下次會再試。」 |

Other lines:

- `measurement` is `unknown`, or `unpriced_models` is not empty: 「這次的花費無法量測（<原因>），帳本記為 unknown，不會影響預算建議。」 Name a model that needs a price in `[prices]`.
- A script error on stderr (for example a task id that is already recorded): show the line as it is and say the row was not written.
- A sync that stops with any reason except `not-a-clone` is repeated later. For `security-references.toml` the rule is in [`security-review.md`](security-review.md#background-reference-updates); the ledger needs nothing, because the next `record` commits the older row with its own.
