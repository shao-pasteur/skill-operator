# Detailed workflow

Everything this workflow writes into the vault (reports, state reasons, the daily overview, the watchlist index) is in Traditional Chinese. The Chinese search phrases below are kept as is because they find Taiwan financial news best.

Before running any phase, confirm:
1. Today's date and the current time (Taiwan time zone, Asia/Taipei)
2. Whether the vault folder `$TW_STOCK_INVESTING_DIR/Daily/{today}/` exists. If not, create the full subfolder structure (`build_report.py` creates it automatically; reports are written straight into the vault in Obsidian format)
3. Whether today is a Taiwan stock trading day (Monday to Friday, not a national holiday). Check with a web search such as 「台股 今天 {date} 開盤」 or the Taiwan Stock Exchange announcements. On a non-trading day, write one line to `logs/run_{HHMM}.log` and stop; skip everything below.

---

## Phase 1: pre-market briefing

### Step 1.1 — Collect US market and world news highlights
Use the web search tool with queries such as:
- 「美股 收盤 {yesterday's date}」, 「S&P500 那斯達克 道瓊 費城半導體 收盤」 (US closes)
- 「Fed 利率 最新」, 「地緣政治 供應鏈 台股 影響」 (Fed rates; geopolitics and supply-chain impact on Taiwan stocks)

Capture only the highlights (percentage moves, main drivers, potential impact on Taiwan heavyweights and the semiconductor supply chain) and summarize them in 3–6 bullet points. Do not translate whole articles.

### Step 1.2 — Decide the 3 hot industries
Search for phrases such as 「台股 今日 熱門族群」, 「台股 早盤 焦點股」, 「台股 概念股 今日」 (today's hot groups, morning focus stocks, today's theme stocks). Read 2–3 financial news articles (common sources such as MoneyDJ, cnyes, Economic Daily News and Commercial Times all work), judge the 3 industries getting the most attention today from coverage and volume (for example AI servers, semiconductor equipment, shipping, finance, biotech), and note the reasons briefly.

### Step 1.3 — 9 dynamic + 9 fixed stocks, deduplicated into the state file

**Read the settings first**: `$TW_STOCK_INVESTING_DIR/config.json` (inside the vault; format under "config.json settings" in SKILL.md). If it does not exist, create it from the defaults and write it back. Take `capital_twd` (capital, default 500000) and `fixed_industries` (three fixed industries with three stocks each).

**9 dynamic stocks**: for the 3 hot industries from step 1.2, search the web (for example 「Yahoo奇摩股市 {industry} 類股」 or 「{industry} 概念股 成交值排行」) for the top 3 stocks by trading value or market cap today. Record each symbol and name and mark it `source: dynamic`.

**9 fixed stocks**: take `fixed_industries` from `config.json` as is (memory / electronic components / shipping, three each) and mark them `source: fixed`.

**Deduplicate**: merge the dynamic and fixed stocks and keep one entry per `symbol` (on a duplicate, keep the `dynamic` entry and note `also_fixed: true`), at most 18 stocks. Write them to:

```
state/selected_stocks.json
```

Format (names and reasons are in Chinese because they appear in the reports):
```json
{
  "date": "2026-07-13",
  "capital_twd": 500000,
  "dynamic_industries": [
    {"name": "半導體", "reason": "簡短判斷依據"},
    {"name": "AI伺服器", "reason": "..."},
    {"name": "航運", "reason": "..."}
  ],
  "fixed_industries": ["記憶體", "電子元件", "航海"],
  "stocks": [
    {"symbol": "2330", "name": "台積電", "industry": "半導體", "source": "dynamic"},
    {"symbol": "2408", "name": "南亞科", "industry": "記憶體", "source": "fixed"},
    ...at most 18 stocks after deduplication
  ]
}
```

**Phases 2 and 3 read this file first on every run; never pick stocks again.**

### Step 1.4 — Fetch historical closes and compute the Bollinger baseline
For these 9 stocks, use the TWSE STOCK_DAY endpoint in `references/data_sources.md` to fetch at least the last 20 trading days of closing prices. If the environment has the `data-context-extractor`, `explore-data` and `validate-data` skills, use them after fetching to understand the fields, explore the data and check for missing or abnormal values. Once the data is clean, feed it to `scripts/bollinger.py` to compute the current Bollinger Bands (20-day moving average ± 2 standard deviations) and where the current price sits (see "Working with other data-analysis skills" in SKILL.md).

### Step 1.5 — Produce the pre-market report
Call `scripts/build_report.py` (usage in the script's docstring) with the 9 stocks' data, the Bollinger results, the US market and news summary and the reasons for the industry picks. If the environment has the `create-viz` skill, you can use it to make better charts than the built-in matplotlib ones and embed those; otherwise the built-in charts are fine. The script:
- Writes `reports/0850_premarket.md`
- Draws a price + Bollinger Band chart for each stock into `charts/`
- Saves this run's signal states to `state/signals_state.json` (the first run has nothing to compare with, so no notification)

---

## Phase 2: intraday updates (09:00–12:00, every 30 minutes)

### Step 2.1 — Read the selected stocks
Read `state/selected_stocks.json` to get the 9 stocks. **Do not re-judge the hot industries or pick stocks again.**

### Step 2.2 — Fetch real-time prices
Use the TWSE real-time quote endpoint (`mis.twse.com.tw`) in `references/data_sources.md` to fetch each of the 9 stocks' current price, open, high and low once.

### Step 2.3 — Recompute Bollinger positions
Pass the latest prices to `scripts/bollinger.py` to get each stock's current band position (for example `below_lower` / `near_lower` / `within` / `near_upper` / `above_upper`).

### Step 2.4 — Compare signals and notify
`scripts/build_report.py` reads the previous states from `state/signals_state.json` and compares them with this run:
- A stock's state changed (especially to `below_lower` or `near_lower`, which technical analysis often treats as a potential support or entry zone) → mark it in the report with 「⚠️ 訊號變化」 and trigger a macOS system notification
- No change → update the report normally without a special alert

### Step 2.5 — Update the report
Write `reports/{HHMM}_update.md`, update the matching charts and update `signals_state.json`.

---

## Phase 3: pre-close sell-zone tracking (`phase: close_watch`, 12:30–13:25 every 30 minutes; after 13:30 the summary `phase: close_summary`)

The flow is almost the same as phase 2 (read the selected stocks → fetch the latest prices → compute the Bollinger Bands → compare signals → update the report). The difference is the report's focus: which zone each stock leans toward technically and how similar positions are usually read in technical analysis, to help the user decide for themselves whether to adjust positions before the close. **Never give a precise "sell at this time" prediction**, and never use assertive language.

On the first run after the 13:30 close, also write `reports/summary_close.md`, summarizing each stock's price change from open to close, how many times and when its Bollinger signal changed, and a review of the day's news and industry highlights.

**Write this closing summary for stock-market beginners** (see "Closing summary for beginners" in SKILL.md). Include: a plain "what happened today", a glossary (Bollinger Bands, upper/middle/lower band, %B and what each position means — explain only, no buy/sell conclusions), a plain-language technical note for each stock, a **neutral capital-math** table based on `capital_twd` (capital, default 500,000: the cost of one lot, about how many lots the capital buys and the percentage of capital, labeled as not a recommendation to buy), and general risk reminders for beginners.

⚠️ **Never** write "these stocks are good buys / should be sold" or "split the 500,000 like this" in the summary — that is personalized investment advice, which this skill does not give. The capital math is only arithmetic ("with this capital, one lot of each stock costs about this much and you can afford this many lots") with no recommendation. `python3 scripts/build_report.py --input payload.json --capital 500000` adds the neutral capital-math table automatically.

If the environment has the `build-dashboard` skill, this step suits it well: merge the day's snapshots into one dashboard instead of a plain-text Markdown summary. The `analyze` skill also fits here to add technical analysis beyond Bollinger Bands.

### Step 3.x — Write the Obsidian index after the close (required after the closing summary)
Once the reports are in the vault, add the two files used for navigating in Obsidian (see "Obsidian format rules" in SKILL.md):
1. **The daily overview `Investing/Daily/{date}/台股日報 {date}.md`** (dated file name, not README): frontmatter (`tags: [investing, daily-stock]`, `date`); content = a one-sentence summary, a table of the 15 stocks' changes and closing band positions, the day's signal trail (premarket → update → close), wikilinks to each report such as `[[0850_premarket]]` and `[[summary_close]]`, and the disclaimer at the end.
2. **Update the "daily index" in `Investing/watchlist.md`**: add a line `- [[台股日報 {date}|{date}]] — 一句話重點` (a one-sentence highlight).

---

## Suggested structure for every report

The report itself is in Traditional Chinese:

```markdown
# 台股追蹤報告 — {日期} {時間}（階段：開盤前 / 盤中更新 / 收盤前追蹤）

## 市場背景
（美股重點、國際新聞重點 — 只有開盤前報告需要完整寫，盤中更新可以省略或只留一行提醒）

## 今日熱門產業與選股邏輯
（3 個產業＋判斷依據 — 只有開盤前報告需要完整寫）

## 9 檔股票技術面追蹤

### {代號} {名稱}（{產業}）
- 目前價格：xxx（漲跌 x.xx%）
- 布林通道：上軌 xxx／中軌(20MA) xxx／下軌 xxx
- 目前位置：{狀態描述}
- ⚠️ 訊號變化（如果有）：從 {舊狀態} 變成 {新狀態}
- 圖表：![](../charts/{代號}_bollinger.png)

（9 檔重複上面格式）

## 免責聲明
（照抄 SKILL.md 裡的免責聲明文字）
```

What each section holds: market background (US and world news; full only in the pre-market report), today's hot industries and why (pre-market only), each stock's price, bands, position, any signal change and its chart, and the disclaimer copied from SKILL.md.
