# tw-stock-vault-sync and related skill changes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manually triggered skill that copies a trading day's tracker results into per-stock and per-industry pages of the Obsidian `Investing` folder, stop the tracker from maintaining `watchlist.md`, and point `obsidian-daily-review` at Knowledge Base tech folders for its tag vocabulary.

**Architecture:** `tw-stock-vault-sync` is a `SKILL.md` plus one stdlib-only Python script that reads `Daily/<date>/state/*.json` and rewrites marker-delimited tables. The tracker loses its watchlist step; links move from `[[watchlist]]` to `[[Investing]]`.

**Tech Stack:** Python 3 stdlib, pytest (repo `make test`), Agent Skills `SKILL.md`.

**Spec:** the vault design note (section 3.6, Investing), summarized in Global Constraints below.

## Global Constraints

- Public repo: no absolute home paths; the Investing folder comes from `TW_STOCK_INVESTING_DIR`.
- Output text in the vault is Traditional Chinese; skill instructions are English.
- Never write buy/sell or allocation advice; pages end with the tracker's Chinese disclaimer.
- Sync only when `Daily/<date>/reports/summary_close.md` exists; otherwise exit non-zero with a clear message.
- Tables are keyed by date: re-running a date replaces that row.
- `Investing.md` sections are delimited by `<!-- sync:recent:start/end -->`, `<!-- sync:stocks:start/end -->`, `<!-- sync:industries:start/end -->`; only text between markers changes.
- Industry aliases come from `config.json` `industry_aliases` (default `{"航運": "航海"}`); `/` in file names becomes `・`.
- Industry pages get a row only for industries with a reason that day (the dynamic, hot industries).

## Review Focus

- Re-running the same date leaves every file byte-identical.
- A date without `summary_close.md` writes nothing.
- `Investing.md` without markers is not modified and the script reports it.
- A stock in two industries on one day lists both.
- An industry name with `/` produces a valid file name and a working link.

---

### Task 1: obsidian-daily-review prefers Knowledge Base tech folders as tags

**Files:** Modify `plugins/research/skills/obsidian-daily-review/SKILL.md`

- [ ] Step 1: In "Collect the vocabulary", add the names of the folders directly under the vault's `Knowledge Base/` as the preferred technology tags (lowercase folder names).
- [ ] Step 2: `make build && make check` → 0 errors. Commit `feat(research): prefer Knowledge Base tech folders as daily-review tags`.

### Task 2: tw-stock-vault-sync skill

**Files:** Create `plugins/finance/skills/tw-stock-vault-sync/SKILL.md`, `.../scripts/sync.py`; tests where the repo's pytest config collects them.

- [ ] Step 1: Write failing tests for the Review Focus lines using a temp Investing folder fixture.
- [ ] Step 2: Implement `sync.py --date YYYY-MM-DD [--investing-dir PATH]`.
- [ ] Step 3: `make test && make build && make check` → pass. Commit `feat(finance): add tw-stock-vault-sync skill`.

### Task 3: tracker stops maintaining watchlist.md

**Files:** Modify `plugins/finance/skills/tw-stock-daily-tracker/SKILL.md`, `references/workflow.md`, `scripts/build_report.py`

- [ ] Step 1: Remove the "add the day to watchlist.md daily index" step; mention `tw-stock-vault-sync` as the follow-up the user runs.
- [ ] Step 2: Replace `[[watchlist]]` links with `[[Investing]]`.
- [ ] Step 3: `make test && make build && make check` → pass. Commit `refactor(finance): hand the vault index over to tw-stock-vault-sync`.
