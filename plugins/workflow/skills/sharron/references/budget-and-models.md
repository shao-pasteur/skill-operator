# Budget and models

Which model tier does which work, how hard a task is, what to do when a unit fails, how to watch spend, and what to write when work has to stop.

Contents:

- [Tiers](#tiers)
- [Difficulty and effort](#difficulty-and-effort)
- [Escalation ladder](#escalation-ladder)
- [Overrun check](#overrun-check)
- [Checkpoints](#checkpoints)

## Tiers

| Tier | Meaning |
|---|---|
| T0 | Scripts, no model |
| T1 | Cheapest model: repetitive work |
| T2 | Middle model: the default |
| T3 | Strongest model |

Each platform maps T1/T2/T3 to models in the config (`platforms.<platform>.models`). On Claude Code the defaults are `haiku`, `sonnet` and `opus`. `sh <skill>/scripts/run.sh config.py show` prints the mapping in effect.

Choosing:

- T3 for complex trade-offs, or R3 and above.
- T2 for moderate, verifiable work.
- T1 for repetitive, automatically verifiable R0–R1 work.
- When unsure, T2.

Role defaults are in `delegation.md` (Roles and tiers). A rule such as "T3 for R3 and above" can raise a role's tier but the config default is the starting point.

**Single-model platforms** (`work`): every tier maps to the same model. Tiers still decide scope and effort. On such a platform the "one tier up" rung of the ladder cannot change the model. It still runs, as a fresh subagent with a rewritten brief that includes the analysis of the earlier failure in `previous_attempts`.

## Difficulty and effort

Rate the task from 1 to 5 during intake.

| Difficulty | Meaning |
|---|---|
| 1 | A single lookup or a direct answer |
| 2 | A few sources and one deliverable |
| 3 | Multiple steps with verification |
| 4 | Several subagents or real trade-offs |
| 5 | Long, multi-session or high-stakes |

Effort follows from difficulty:

| Difficulty | Subagents | Tool calls per subagent (`max_tool_calls`) |
|---|---|---|
| 1 | None (sharron uses at most 10 tool calls) | — |
| 2 | 0–1 | ≤ 10 |
| 3 | 1–3, including a verifier | ≤ 15 |
| 4 | 2–4 | ≤ 15 |
| 5 | Up to 10, with clearly divided responsibilities | ≤ 20 |

More than 5 subagents needs a confirmation first (L3). At most `max_parallel_subagents` (default 3) run at once.

The budget for the task comes from `sh <skill>/scripts/run.sh finance.py suggest --playbook <id> --difficulty <1-5>`. It prints the amount in equivalent USD with its basis. The script uses only measured ledger rows of successful tasks (outcome `done`, every checked claim confirmed, no correction) on the same platform: the 80th percentile of similar past tasks when there are at least 5, a fit across difficulties when there are at least 10 on the playbook, otherwise the config default for the difficulty.

## Escalation ladder

When a unit fails (a `failed` or `partial` report, a missed done-when, repeated identical tool calls, or no progress):

1. Retry once with a fresh subagent at the same tier. Put the failure and its error text in `previous_attempts`.
2. Retry once with a fresh subagent one tier up.
3. Send the unit to the diagnostician (T3) for root-cause analysis, with every earlier attempt in `previous_attempts`.
4. Ask the user (L4): a decision card with what was tried, the diagnosis and the options.

Reaching `max_tool_calls` ends a unit with a partial report, and that counts as a failure here. Never retry with the same subagent.

A `blocked` report is not a failure and is not retried. The unit could not continue for a reason a retry will not remove (it needs an answer, an approval or access). Read `not_done` and `risks`, then either settle it through the decision gate (an approval is an L3 or L4 matter, see `decisions-and-risk.md`) or, when only the user can unblock it, ask the user and pause the task with a checkpoint (see below). Retry only after the blocker is gone, with a fresh subagent and the answer in `decisions`.

## Overrun check

Check spend after each batch of subagents finishes and before starting the next batch. On Claude Code:

```
sh <skill>/scripts/run.sh finance.py usage --since <task start, ISO time> --budget <suggestion in USD>
```

The script prints the measured cost, the limit (budget times `overrun_factor`, default 1.5) and `over_budget`. When `over_budget` is true:

1. Pause non-urgent work and let running units finish or cancel them cleanly.
2. Ask whether to continue, as an L3 confirmation (see `decisions-and-risk.md`).
3. If the user says yes, carry on and note the decision. If not, write a checkpoint and stop.

On other platforms, use whatever usage the platform reports. When usage cannot be measured, the overrun check is skipped: the ledger row for the task is recorded with cost `unknown`, and no overrun is claimed.

Pass `--agents <ids>` to measure only named subagent transcripts, or `--exclude-agents <ids>` to leave some out (for example a maintenance run that overlaps the task).

## Checkpoints

Write a checkpoint when the platform reports a usage warning or limit, or when a task pauses for any reason (waiting for the user, blocked):

1. Stop non-urgent work and wrap up or cancel running units cleanly.
2. Write the checkpoint under the task in `MEMORY.md`, in Traditional Chinese, using the template below.
3. Set the task status to paused or waiting.

Step 0 of every later task lists paused and waiting tasks first, so nothing is dropped.

```
檢查點（<日期時間>）
- 已完成：…
- 目前狀態：…
- 下一步：…
- 如何接續：對 sharron 說「<接續用的提示>」；相關檔案與連結：…
- 待決定：…（需要你回答的事）
```
