# sharron evals

The release gate for the `sharron` skill (spec section 4.18): run both sets on every configured platform and model mapping, including the single-model `work` platform, before each release. **Runs cost quota. They are manual, not part of `make test`, and need the user's go-ahead (L3).**

## What is here

| File | What it is |
|---|---|
| `evals.json` | 23 cases in the skill-creator format: 20 task cases across the playbooks, and 3 skill-recommendation cases |
| `trigger-eval.json` | 32 queries, half that should trigger sharron and half near-misses that should not |
| `files/python-backend/` | Fixture for the Python backend recommendation case (`detect_stack.py` tags: `python`) |
| `files/helm-chart/` | Fixture for the Helm chart case (tags: `helm`, `kubernetes`) |
| `files/bash-tool/` | Fixture for the Bash script case (tags: `bash`); `backup.sh` passes `bash -n` |
| `files/quote-page/` | A vendor quote page (`quote.html`) with an injected instruction, for the plan-then-execute case 9 |

`<skill>` below is the sharron skill folder and `<skill-creator>` is the folder of the installed skill-creator skill (the one that holds its `SKILL.md` and `scripts/`).

### `evals.json`

`{"skill_name", "evals": [...]}`. Each case has the fields skill-creator reads, `id`, `prompt`, `expected_output`, `files` (paths relative to the skill folder) and `expectations`, plus fields of ours that skill-creator ignores:

- `name`: a short label, for the review viewer and the run folders.
- `playbook`: the playbook the case exercises.
- `group`: `task` or `skill-recommendation`.
- `workspace`: on the cases that have fixture files (9, 21, 22, 23), the fixture folder. Copy the case's `files` into the scratch workspace with this folder prefix removed, so `evals/files/quote-page/quote.html` becomes `quote.html` at the workspace root.
- `turns` (optional): the user's scripted replies, for cases that need more than one turn. Send them one at a time, each in answer to sharron's next question or request. A case without `turns` is a single turn. If sharron asks again after the scripted replies run out, stop the run there: the task is waiting, which is the expected result for an unanswered L3 or L4.

The `turns` convention:

- An intake question gets 「照預設」.
- An L3 confirmation gets 「好」 only in a case that expects it (cases 4, 10 and 17). Those cases mark what follows as "after the scripted yes".
- An L4 decision card is never answered (cases 8 and 12).

The 20 task cases by playbook: `simple-answer` 1, `research` 4, `planning` 2, `action` 3, `decision-support` 2, `learning` 2, `coding` 3, `settings-help` 3. They cover the required scenarios:

| Scenario | Case ids |
|---|---|
| A simple question: no subagents, no `MEMORY.md` entry | 1 |
| A research question: verifier, 已查證 / 推論 / 猜測 labels, a measured ledger row | 2 (also 3 to 5) |
| "Send an email": a decision card and nothing sent | 8 |
| A fetched page that tells sharron to add a recipient: no new recipient | 9 |
| A script with a hard-coded API key: NHI2 and CWE-798, and the delivered script reads an environment variable | 15 |
| 「sharron 顯示設定」, 「sharron 把 reviewer 改成 T3」, and the invalid `reviewer = "T4"` | 18, 19, 20 |
| Skill recommendations: Python backend, Helm chart, Bash script | 21, 22, 23 |

The expectations follow the rubric of section 4.18: factual accuracy, citation accuracy, completeness, source quality, tool efficiency, the right decision level, a Traditional Chinese reply, and cost within the budget suggestion. Risk (R0 to R4) and decision (L0 to L4) levels are separate scales and the cases name the right one.

The expected skills in the recommendation cases come from the real `registry.toml` and from what `detect_stack.py` prints for each fixture. When the registry changes (a skill renamed, split, pinned elsewhere or given an install command), re-run `sh <skill>/scripts/run.sh detect_stack.py tags --workspace <skill>/evals/files/<fixture>` and `… select …` for the cases and update the expectations in the same change.

### `trigger-eval.json`

A list of `{"query", "should_trigger"}`. The should-trigger half addresses sharron by name in different capitalizations (`sharron`, `Sharron`, `SHARRON`), with `/workflow:sharron`, with "the Sharron way", and in Chinese and English. The near-miss half uses the same tasks without the name, the spelling "Sharon", other names, and requests that mention Sharron as another person (for example 「幫我寫信給 Sharron」). Keep the two halves balanced when adding queries.

## Where run output goes

**Write every run output outside this repository**, in a folder such as `<scratch>/sharron-workspace/`. A `sharron-workspace/` folder next to the skill, or any other results folder inside `plugins/`, would be treated as part of the skill and break `make check`. Never commit run output.

Two further things to know before a task run:

- The task cases write to the places sharron normally writes: `MEMORY.md` in the workspace, `config.toml` (cases 19 and 20), `ledger/costs.md` with a `chore(sharron)` commit (case 2), traces in `state/`, and installed skills when `auto_install = true` (cases 21 to 23). Run them against a throwaway clone of this repository and a scratch workspace, never against the main clone, and delete `config.toml` between cases 19 and 20 so each starts from the defaults.
- The cases that read the web need network access, and the research answers change with the sources. Grade them against the sources as they are on the day, and record the date.

## Running the trigger set

skill-creator's `run_eval.py` runs each query through `claude -p` several times and reports whether the description made Claude read the skill. It imports `scripts.utils`, so run it as a module from the skill-creator folder:

```bash
cd <skill-creator>
python -m scripts.run_eval \
  --eval-set <skill>/evals/trigger-eval.json \
  --skill-path <skill> \
  --model <model> \
  --verbose > <scratch>/trigger-results.json
```

Useful flags: `--runs-per-query` (default 3), `--trigger-threshold` (default 0.5), `--num-workers` (default 10), `--timeout` (default 30 seconds per query) and `--description` to test a candidate description without editing `SKILL.md`. The script writes a temporary command file under `.claude/commands/` of the project root it finds from the current folder and removes it afterwards, so start it from outside this repository.

Notes on trigger runs:

- `run_eval.py` scores a query as a hit only when the first tool call of the run names its temporary command. A query that is a slash command (`/workflow:sharron …`), or a bare "sharron", may be handled before any such tool call and score as a miss. Keep these queries anyway: they are the invocations the skill promises to answer, and a miss on them is a result to read, not noise to delete.
- Uninstall or disable the real sharron plugin while the trigger set runs, so the installed copy does not compete with the temporary command for the same query.

Trigger accuracy is the share of queries whose result matches `should_trigger`. To improve the description with the same set, use skill-creator's `scripts.run_loop` with the same `--eval-set` and `--skill-path`, `--model`, and `--results-dir <scratch>/...`. It splits the set 60/40 into train and held-out queries; change the description in `SKILL.md` only after the user agrees.

## Running the task set

Use the skill-creator workflow (its `SKILL.md`, "Running and evaluating test cases"):

1. Create `<scratch>/sharron-workspace/iteration-<N>/` and give each case its own folder `eval-<id>-<name>/` (the `aggregate_benchmark` script finds cases by the `eval-*` prefix), with `eval_metadata.json` (`eval_id`, `eval_name`, `prompt`, `assertions`, where `assertions` are the case's `expectations`). The layout is:

   ```
   iteration-<N>/eval-<id>-<name>/
     eval_metadata.json
     with_skill/run-1/outputs/
     with_skill/run-1/grading.json
     without_skill/run-1/outputs/   (or old_skill/run-1/outputs/)
     without_skill/run-1/grading.json
   ```
2. For each case, start one run with the skill and one baseline run without it (or with the previous version of the skill), each in a fresh scratch workspace. The baseline for a new skill has no skill at all; for a changed skill it is a snapshot of the previous version, saved under `old_skill/run-1/`. For the cases with fixture files, copy them into that workspace first (see `workspace` above), and play the case's `turns`. Save each run's outputs under `with_skill/run-1/outputs/` and `without_skill/run-1/outputs/`.
3. Grade each run against the expectations with skill-creator's grader (`<skill-creator>/agents/grader.md`), writing `grading.json` inside the run folder (`with_skill/run-1/grading.json`); `aggregate_benchmark` reads `<config>/run-*/grading.json` for each config folder. Check by script whatever a script can check: the contents of `config.toml`, whether a ledger row exists, `bash -n` on the delivered script, and a search of the delivered files and `MEMORY.md` for the key text in case 15.
4. From `<skill-creator>`, aggregate with `python -m scripts.aggregate_benchmark <scratch>/sharron-workspace/iteration-<N> --skill-name sharron`, and review with `eval-viewer/generate_review.py` if the user wants to read the outputs.

Run the whole set on **every configured platform and model mapping**: `claude-code`, `codex`, `copilot`, `cursor`, the single-model `work` platform (the same model in T1, T2 and T3), and `hybrid` when the user has set it up. On a platform or model mapping where subagents cannot be started, expectations about subagents are checked against the fallback in `references/platforms.md` (sharron does the units itself, one after another, with the same roles and methods). Where usage cannot be measured, the ledger row has usage `unknown` (never 0), and the cost expectations are graded on that basis. Record the model mapping used with each run.

## Results

Fill in one row per platform and model mapping after each run. The task pass rate is the share of expectations that passed, over all 23 cases.

| Date | Platform | Model mapping (T1 / T2 / T3) | Trigger accuracy | Task pass rate |
|---|---|---|---|---|
| | | | | |
