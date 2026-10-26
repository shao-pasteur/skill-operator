---
name: tw-stock-daily-tracker
description: Tracks Taiwan stocks on trading days before the open, during the session (every 30 minutes from 9:00 to 12:00) and before the close. Collects the previous night's US market moves and world news, picks the three industries with the most news attention and their top three stocks by trading value or market cap (9 dynamic picks), adds the top three stocks of three fixed industries (memory, electronic components, shipping), runs Bollinger Band analysis on up to 18 stocks, and writes text and chart reports in Obsidian format into the vault's Investing/Daily/ folder, with a beginner-friendly closing summary. Reports are in Traditional Chinese. Use when the user asks for a Taiwan stock morning briefing, intraday tracking, Bollinger Band screening, today's hot industries or a pre-close analysis (for example 「台股晨間簡報」「台股盤中追蹤」「布林通道選股」「今日熱門產業分析」「台股收盤前分析」), or wants scheduled runs on trading days. Output is educational and not investment advice.
compatibility: Requires Python 3, network access (TWSE and news sources) and the TW_STOCK_INVESTING_DIR environment variable pointing at the Investing folder of an Obsidian vault. Scheduling supports macOS launchd only.
metadata:
  web: "false"
---

# Taiwan stock daily tracker (tw-stock-daily-tracker)

A three-phase technical tracking workflow for Taiwan stocks: **pre-market briefing → intraday updates → pre-close sell-zone tracking**. It is designed for Claude Code (the local CLI) with `cron`/`launchd` scheduling, because it needs real write access to the local file system and repeatable web search and fetching.

## Core rules (follow on every run)

1. **Only organize technical information and explain it; never give investment advice.** Always use descriptive language about Bollinger Band position and technical signals, for example "the price touched the lower band, which technical analysis often treats as a potential support zone". **Never** write directive or judgmental phrases such as "buy now", "this one will rise", "buy X lots", or "these are good buys and those should be sold".
   - **Explaining for beginners is not advice.** The closing summary helps beginners understand what a signal means and how technical analysis usually reads it, but it **must not** conclude for the user whether to buy, sell or whether a stock is suitable.
   - **The capital field is only for neutral affordability math, never for allocation advice.** You may show plain arithmetic such as "one lot is 1,000 shares, one lot of this stock costs about X at the current price, the configured capital buys about N lots". **Never** write position or allocation recommendations such as "split the 500,000 like this" or "buy X lots of this and Y lots of that". If the user asks for buy/sell calls or allocation, explain that neither this skill nor Claude gives personalized investment advice, and suggest they decide themselves or consult a licensed advisor.
2. **Attach the disclaimer at the end of every report** (see "Disclaimer" below), word for word.
3. **Pick the day's stocks only once, before the open**: 9 dynamic stocks (3 hot industries × 3) plus 9 fixed stocks (memory / electronic components / shipping × 3), at most 18 after removing duplicates. Every later intraday or pre-close update reuses the same list (unless the user asks to change it) so the analysis stays consistent.
4. **This is not real-time monitoring.** Each run is a single scheduled snapshot; comparing it with the previous run's signals simulates "live updates" and "notify on signal change". Tell the user about this limitation honestly and never imply second-by-second monitoring.
5. Before running, confirm today is a **Taiwan stock trading day** (Monday to Friday, not a national holiday or typhoon day). If unsure, check with a web search. On a non-trading day, skip and write one log line.
6. **Write every output in Traditional Chinese.** These instructions are in English, but everything the skill writes into the vault or shows the user (reports, the daily overview, the watchlist index, macOS notifications) stays in Traditional Chinese, and the disclaimer below is copied in Chinese exactly as written.

## The three phases

The detailed steps are in `references/workflow.md`. **Read that file before every run.** The overall structure:

### Phase 1: pre-market briefing (suggested schedule 08:45–08:55)
- Use web search to collect the previous night's US market closes (S&P 500, Nasdaq, Dow Jones, the Philadelphia Semiconductor Index, key heavyweight stocks)
- Use web search to collect world news that affects Taiwan stocks (Fed moves, geopolitics, supply-chain news and so on)
- Decide the **3 industries** with the most news attention today (judge by news volume and discussion; the user does not need to name them)
- For each hot industry, pick the **top 3** stocks by trading value or market cap, giving **9 dynamic stocks**
- **Also add the top 3 stocks of 3 fixed industries (9 fixed stocks)**: memory, electronic components and shipping. These lists live in `fixed_industries` in `config.json` (the user can edit them); the defaults are under "config.json settings" below
- **Remove duplicates** between the dynamic 9 and the fixed 9 (a stock picked dynamically that is also on a fixed list counts once), save the result to the day's state file `state/selected_stocks.json` (reused by later phases), and mark each stock `source: dynamic | fixed`
- Fetch recent closing prices for these stocks (at least 20 trading days) to compute the Bollinger Band baseline
- Produce the pre-market briefing report

### Phase 2: intraday updates (suggested schedule: every 30 minutes from 09:00 to 12:00)
- Read the 9 stocks chosen in phase 1 (do not pick again)
- Fetch the latest or real-time price for these 9 stocks
- Recompute Bollinger Band positions with `scripts/bollinger.py`
- Compare with the previous signals: when a stock's position changes (for example from "inside the band" to "touching the lower band"), highlight it and trigger a local notification (a macOS `osascript` notification)
- Update the day's report file

### Phase 3: pre-close sell-zone tracking (suggested schedule: every 30 minutes from 12:30 to 13:25; the Taiwan market closes at 13:30)
- Read the same 9 stocks, fetch the latest prices and recompute the Bollinger Bands
- For each stock, describe from its Bollinger position which zone it leans toward technically and how similar positions are usually read, **not** a precise prediction of when to sell
- Compare with the previous run; highlight signal changes and trigger a notification
- After the close (the first run after 13:30), write the day's summary report for **stock-market beginners** (see "Closing summary for beginners" below)

## Required settings

This skill writes reports into the user's Obsidian vault. The environment variable `TW_STOCK_INVESTING_DIR` gives the path of the vault's `Investing` folder (for example `/Users/<you>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault name>/Investing`).

- Before running, check that `echo "$TW_STOCK_INVESTING_DIR"` prints a value.
- When the run is scheduled in the background (launchd, cron or `claude -p`) and nobody can answer questions: if the variable is not set, **do not ask; stop** and print the error "TW_STOCK_INVESTING_DIR is not set; add this environment variable to the schedule settings".
- In an interactive run with the variable unset, first ask the user for the path of the vault's Investing folder, pass it to `build_report.py` for this run as `--base-dir "<path>/Daily" --config "<path>/config.json"`, and suggest adding `export TW_STOCK_INVESTING_DIR="<path>"` to their shell profile (for example `~/.zshrc`).
- The variable must also be set before installing the launchd schedule (`scripts/install_launchd_jobs.sh`); the installer writes its value into every plist.

## Output location (written straight into the Obsidian vault)

Every report is written **in Obsidian format** under the vault's `Investing/Daily/` (no longer under `04_stock/daily_analysis/`):

```
$TW_STOCK_INVESTING_DIR/
├── config.json                       ← settings shared across days (capital, fixed industries)
├── watchlist.md                      ← watchlist plus daily index (index updated after the close)
└── Daily/{YYYY-MM-DD}/
    ├── 台股日報 {YYYY-MM-DD}.md        ← daily overview written by Claude after the closing summary (see below; the date in the file name makes it easy to spot in Obsidian)
    ├── reports/
    │   ├── 0850_premarket.md         ← every report has Obsidian YAML frontmatter
    │   ├── 0900_update.md
    │   ├── ...
    │   └── summary_close.md          ← closing summary (for beginners)
    ├── charts/{symbol}_bollinger.png ← Bollinger chart (embedded in reports with the relative path ![](../charts/..), which Obsidian displays)
    ├── state/{selected_stocks,signals_state}.json
    └── logs/run_{HHMM}.log
```

Missing folders are created automatically (`mkdir -p`). `build_report.py` derives the default `--base-dir` and `--config` from `TW_STOCK_INVESTING_DIR`, so once the variable is set it runs as is.

### Obsidian format rules (follow for every file you write)
- **Every report starts with YAML frontmatter**: `tags: [investing, daily-stock, {phase}]`, `date`, `phase`, `time`, `source: tw-stock-daily-tracker`. (`build_report.py` adds it automatically; add it yourself to any extra note you write by hand.)
- Start reports with an **Obsidian wikilink** to related notes, such as `> 追蹤清單見 [[watchlist]]。`
- Embed charts with the relative path `![](../charts/{symbol}_bollinger.png)` (`build_report.py` does this).
- **After the closing summary, write or update the daily overview `台股日報 {YYYY-MM-DD}.md`** in that day's folder. **Use the dated file name, not a generic name like README that is unreadable in Obsidian's file list or graph.** Include frontmatter, a one-sentence summary, a table of the 15 stocks' changes and closing band positions, the day's signal trail (premarket → update → close), wikilinks to each report such as `[[0850_premarket]]` and `[[summary_close]]`, and the disclaimer at the end. Also add the day to the "daily index" of `watchlist.md` (`[[台股日報 {date}|{date}]]`).

## Bollinger Band calculation and report generation

`scripts/bollinger.py` computes band positions. `scripts/build_report.py` assembles the Markdown report, draws charts with matplotlib and triggers a macOS notification when a signal changes. Both scripts document their usage in the docstring at the top; check the options with `python3 scripts/bollinger.py --help` and `python3 scripts/build_report.py --help` before running.

Data sources (the official TWSE API endpoints and how to use the real-time quote endpoint) are in `references/data_sources.md`.

## Working with other data-analysis skills

If the environment also has these skills (`analyze`, `explore-data`, `validate-data`, `data-context-extractor`, `write-query`, `create-viz`, `build-dashboard`), let them handle the matching steps first, and treat this skill's `scripts/bollinger.py` and `scripts/build_report.py` as the fallback when they are missing. Suggested mapping:

| Step in this skill | Related skill | Why |
|---|---|---|
| Phase 1 steps 1.1/1.4: understanding the fields after fetching TWSE API or news data | `data-context-extractor` | Extract the data structure and field meanings first so later steps do not misread fields |
| Phase 1 step 1.4: after fetching 20+ days of closing prices | `explore-data` | Explore first (missing values, abnormal gaps, continuity) instead of feeding the data straight into the Bollinger calculation |
| Data checks before the Bollinger calculation | `validate-data` | Check price data for completeness and sanity (negative values, duplicate dates) and flag problems instead of computing anyway |
| Pulling historical prices from a local database or CSV instead | `write-query` | Write the query instead of calling the TWSE API (for example once you build your own price history store) |
| Fuller technical or quantitative analysis beyond Bollinger Bands | `analyze` | Add analysis such as volume changes or RSI to enrich the report |
| Chart generation | `create-viz` | Replace the static matplotlib charts in `scripts/build_report.py` with better visualizations |
| Combining a day's many updates into one overview | `build-dashboard` | Especially suited to the closing summary (`close_summary`): merge the day's 12 snapshots into one dashboard rather than only the last Markdown file |

How to hand data over (input and output formats) follows each skill's own SKILL.md. When you reach the matching step, read that skill's SKILL.md before deciding how to pass the data in. If a mapping here turns out awkward in practice, adapt it; the table is not binding.

## Scheduling (cron / launchd)

After setting this skill up for the user, `references/cron_setup.md` has launchd and crontab examples, including the suggested trigger times for each phase. After setup, remind the user to:

- Check that the jobs are loaded with `launchctl list | grep tw-stock` or `crontab -l`
- Keep the computer on and awake at the scheduled times; launchd handles missed runs somewhat better than cron
- **Explain the risk before installing the schedule**: `scripts/install_launchd_jobs.sh` runs `claude -p --dangerously-skip-permissions`, so background runs never ask for permission. If news or web content carries malicious instructions, the agent may act on them without confirmation. Install only after the user accepts this risk; otherwise they can run each phase interactively by hand.

## config.json settings (editable, read on every run)

Path: `$TW_STOCK_INVESTING_DIR/config.json` (inside the vault, shared across days, not one per day).

**Read this file at the start of every run.** If it is missing or lacks fields, use the defaults below and write the completed defaults back so the user can edit them later.

```json
{
  "capital_twd": 500000,
  "fixed_industries": [
    {"name": "記憶體",   "stocks": [{"symbol": "2408", "name": "南亞科"}, {"symbol": "2344", "name": "華邦電"}, {"symbol": "8299", "name": "群聯"}]},
    {"name": "電子元件", "stocks": [{"symbol": "2327", "name": "國巨"},   {"symbol": "2308", "name": "台達電"}, {"symbol": "2492", "name": "華新科"}]},
    {"name": "航海",     "stocks": [{"symbol": "2603", "name": "長榮"},   {"symbol": "2609", "name": "陽明"},   {"symbol": "2615", "name": "萬海"}]}
  ]
}
```

The industry and company names above are written into the user's vault and appear in the Chinese reports, so they stay in Chinese (memory: Nanya Technology, Winbond, Phison; electronic components: Yageo, Delta Electronics, Walsin Technology; shipping: Evergreen Marine, Yang Ming, Wan Hai).

- `capital_twd`: **capital for buying (editable)**, in New Taiwan dollars. Use the default **500000** if the user has not changed it. It is used only for the **neutral affordability math** in the reports' capital section (see below) and **must not** produce any buy, sell or allocation advice.
- `fixed_industries`: the three fixed industries and their stock lists; the user can add, remove or swap stocks.

## Closing summary for beginners (`close_summary`)

The closing summary (`summary_close.md`) must be readable by **complete beginners**. Suggested sections:

1. **What happened today**: one plain sentence on the market mood and why these stocks closed up or down overall (link it to the overnight US market and the news).
2. **Glossary**: one or two plain sentences for each term the report uses — Bollinger Bands, upper/middle/lower band, %B, what breaking below or nearing the lower band means — so beginners know **how technical analysis usually reads** each signal (for example "breaking below the lower band: the price is relatively low in the short term; some technical analysts see it as oversold, but it can also mean the trend is weakening; both readings exist"). **Explain only; never conclude buy or sell.**
3. **A plain-language technical note for each stock**: translate the Bollinger position into everyday words — where it sits in the band now and how such positions have usually been read — and state clearly that this is not telling the user to buy or sell.
4. **Capital math (neutral, not advice)**: using `capital_twd` as the capital, list plain arithmetic — one lot is 1,000 shares; for each stock, about how much one lot costs at the close, about how many lots the capital buys (rounded down) and about what percentage of the capital one lot is. Start the section with "**以下為資金規模試算，非建議買進任一檔**" (the following is affordability math, not a recommendation to buy any stock).
5. **Reminders for beginners**: technical signals are only one of many references, the past does not predict the future, and general ideas such as buying in stages and managing risk (general principles, not about any specific stock).

⚠️ **Never** put stock-level buy/sell verdicts or allocation advice in the closing summary (or any report), such as "these are good buys / these should be sold" or "split the 500,000 like this". If the user asks explicitly, always reply that neither this skill nor Claude gives personalized investment advice, and suggest they decide themselves or consult a licensed advisor. `scripts/build_report.py` accepts `--capital` and adds the neutral capital-math table automatically.

## Disclaimer (attach to the end of every report, copied word for word)

> 本報告僅整理公開市場資訊與布林通道等技術指標的客觀計算結果，用於個人研究參考，**不構成任何投資建議、亦非邀約買賣任何有價證券**。過往技術訊號不保證未來走勢，投資有風險，請自行判斷並承擔投資決策的風險與責任。本報告非持有證券投資顧問執照者所出具之投資分析意見。

(English meaning, for reference only; reports must use the Chinese text above: this report only organizes public market information and objective calculations of technical indicators such as Bollinger Bands for personal research. It is not investment advice or an offer to buy or sell any security. Past technical signals do not guarantee future movements; investing carries risk, so decide for yourself and bear the responsibility. This report is not an investment analysis opinion issued by a licensed securities investment adviser.)
