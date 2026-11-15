---
name: tw-stock-vault-sync
description: Copies one trading day of tw-stock-daily-tracker results into the Obsidian Investing folder — a page per stock (close, Bollinger Band position, industries), a page per hot industry (the day's news reason and affected stocks), and the overview tables in Investing.md. Run it by hand after the tracker's closing summary. Use when the user asks to sync the Taiwan stock data into the vault, for example 「同步今天的台股資料」「同步 11/14 的台股資料」「把台股日報整理進 Investing」. Pages are in Traditional Chinese and are not investment advice.
compatibility: Requires Python 3 (standard library only) and the TW_STOCK_INVESTING_DIR environment variable pointing at the Investing folder of an Obsidian vault (the same folder tw-stock-daily-tracker writes to).
metadata:
  web: "false"
---

# Taiwan stock vault sync (tw-stock-vault-sync)

Takes what `tw-stock-daily-tracker` produced for one trading day and files it into the vault's `Investing` folder, so each stock and each hot industry has its own page with a history table, and `Investing.md` shows the recent days and an overview. The user triggers it by hand; it is not scheduled.

## Rules

1. **Never write investment advice.** The script copies prices, band positions and the tracker's news reasons. Do not add buy/sell verdicts or allocation suggestions to the pages or to your reply. Every page the script creates ends with the tracker's Chinese disclaimer.
2. **Everything written into the vault is Traditional Chinese.** These instructions are English; the pages, tables and the script's messages are Chinese. Reply to the user in the language they used.
3. **Only the tables between sync markers change.** The user may write their own notes anywhere else on a page or in `Investing.md`; the script never touches that text. Do not edit the synced tables by hand either: the next run overwrites them.

## Required settings

`TW_STOCK_INVESTING_DIR` is the path of the vault's `Investing` folder (for example `/Users/<you>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault name>/Investing`).

- Check it with `echo "$TW_STOCK_INVESTING_DIR"`.
- If it is unset, **ask the user** for the path of their Investing folder and pass it as `--investing-dir "<path>"` for this run. Never guess or search the disk for it. Suggest adding `export TW_STOCK_INVESTING_DIR="<path>"` to their shell profile (for example `~/.zshrc`).

Optional, in `$TW_STOCK_INVESTING_DIR/config.json` (the tracker's settings file):

- `industry_aliases`: an object mapping industry names to the name pages should use, so the same industry gets one page even when the news calls it something else. When the key is missing the default is `{"航運": "航海"}` (shipping, matching the tracker's fixed industry). When it is present it replaces the default.
- `fixed_industries`: read to find which fixed industries a stock marked `also_fixed` also belongs to.

## Running it

1. Work out the date. "Today" means today in Asia/Taipei. A date like 「11/14」 means the most recent such day up to today; turn it into `YYYY-MM-DD`.
2. Run:

   ```bash
   python3 scripts/sync.py --date YYYY-MM-DD
   # or, when TW_STOCK_INVESTING_DIR is unset:
   python3 scripts/sync.py --date YYYY-MM-DD --investing-dir "<path>"
   ```

   Without `--date` it uses today in Asia/Taipei.
3. Report the result by exit code:
   - `0`: synced. List the files the script says it created or updated (it prints them). If it says nothing changed, tell the user the vault was already up to date for that day.
   - `2`: the day is not ready: `Daily/<date>/reports/summary_close.md` or a state JSON is missing, and nothing was written. Tell the user the closing analysis for that day has not run yet (or that it was not a trading day), and that they can run `tw-stock-daily-tracker`'s closing summary first.
   - `3`: the stock and industry pages were written, but `Investing.md` is missing or lacks some markers, so it was left untouched. Show the user the missing markers the script printed and offer the marker block below so they can paste it where they want the tables.
   - `1`: bad arguments or an unreadable file; show the message.

Re-running a date is safe: it replaces that date's rows, and running twice leaves every file byte-identical.

## What it reads

From `$TW_STOCK_INVESTING_DIR/Daily/<date>/` (written by `tw-stock-daily-tracker`):

- `reports/summary_close.md`: only checked for existence, as the sign the day is finished
- `state/selected_stocks.json`: the day's dynamic industries with their reasons, the fixed industries, and the stocks
- `state/signals_state.json`: each stock's last price and Bollinger Band position
- `台股日報 <date>.md` (optional): the daily overview, for its one-sentence summary

## What it writes

### `Stocks/<symbol> <name>.md`

Created when missing, with frontmatter (`tags: [investing, stock]`, `symbol`, `name`), a link back to `[[Investing]]`, a table between `<!-- sync:signals:start -->` and `<!-- sync:signals:end -->`, and the disclaimer. Columns: 日期｜收盤價｜通道位置｜當天所屬產業. One row per date, newest first. 當天所屬產業 lists every industry the stock belonged to that day (its dynamic industry plus any fixed one), as wikilinks to the industry pages, joined with 、. An existing page for the same symbol is reused even if the name changed.

### `Industries/<industry>.md`

Only for industries that had a news reason that day (the tracker's dynamic, hot industries). Same layout with `tags: [investing, industry]`, markers `<!-- sync:news:start -->` / `<!-- sync:news:end -->`, and columns 日期｜消息｜影響個股 (the reason and wikilinks to that day's stocks in the industry). The file name is the alias-normalized name with characters Obsidian cannot use in file names or links (`/ \ : * ? " < > | # ^ [ ]`) replaced by `・`, and every link uses that file name. Fixed industries that were not hot that day get no row, so their links on stock pages stay unresolved until they are.

### `Investing.md`

Must already exist; the script never creates it. Only the text between these markers is regenerated:

```markdown
## 最近交易日
<!-- sync:recent:start -->
<!-- sync:recent:end -->

## 個股
<!-- sync:stocks:start -->
<!-- sync:stocks:end -->

## 產業
<!-- sync:industries:start -->
<!-- sync:industries:end -->
```

- `recent`: 日期｜一句話 for the five most recent days under `Daily/` that have both state files and `summary_close.md`. The date links to `[[台股日報 <date>|<date>]]` when that file exists. The sentence comes from the overview: a line labeled 一句話…： (for example `**一句話總結**：…`), else the first line under a heading containing 一句話, else the first paragraph after the title; — when there is none.
- `stocks`: 個股｜最新收盤｜通道位置｜最後更新, one row per page in `Stocks/`, from its newest row, sorted by symbol.
- `industries`: 產業｜最近熱門日期｜熱門次數, one row per page in `Industries/`, most recent date first.

`|` inside a table cell is written as `\|`, including wikilink aliases.

## Disclaimer (copied word for word from tw-stock-daily-tracker)

> 本報告僅整理公開市場資訊與布林通道等技術指標的客觀計算結果，用於個人研究參考，**不構成任何投資建議、亦非邀約買賣任何有價證券**。過往技術訊號不保證未來走勢，投資有風險，請自行判斷並承擔投資決策的風險與責任。本報告非持有證券投資顧問執照者所出具之投資分析意見。
