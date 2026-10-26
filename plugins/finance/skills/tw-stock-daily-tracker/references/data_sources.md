# Data sources

## 1. Historical daily closes (for the Bollinger baseline) — TWSE STOCK_DAY

The Taiwan Stock Exchange's monthly per-stock daily trading data:

```
https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={YYYYMM01}&stockNo={symbol}
```

- Pass the first day of the month as `date` (for example `20260701`) to get the whole month's daily OHLC data
- At least 20 trading days are needed. If the current month has fewer (for example early in the month), also fetch the previous month
- Fetch it with `curl` in bash, for example:

```bash
curl -s "https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20260701&stockNo=2330"
```

Each row of the returned `data` field is `[date, shares traded, trading value, open, high, low, close, change, number of trades]`; the close is index 6.

## 2. Real-time / latest price — TWSE MIS real-time quotes

```
https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{symbol}.tw
```

For example, TSMC:
```bash
curl -s "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw"
```

Commonly used fields in the returned JSON:
- `z`: latest trade price (real time during the session; `-` before the first trade, in which case use the open `o` or the previous value)
- `y`: previous close
- `o`: today's open
- `h`: today's high
- `l`: today's low
- `tv`: volume of the latest trade

Query several stocks at once by separating them with `|`: set `ex_ch` to `tse_2330.tw|tse_2317.tw|...`.

⚠️ This is the public endpoint used by the "intraday chart" page on the TWSE website. Outside trading hours it may return empty values or the previous trading day's close; that is normal and should not be treated as an error.

## 3. US market and world news

There is no fixed API; use Claude Code's built-in web search. Capture:
- The closing moves of the three major US indexes (S&P 500, Nasdaq, Dow Jones) and the Philadelphia Semiconductor Index
- US stocks closely tied to Taiwan heavyweights (for example Nvidia, Apple, AMD) and how they moved
- Macro and geopolitical headlines and highlights (Fed decisions, tariffs, supply-chain events and so on)

## 4. Hot industries and trading-value rankings

There is no single stable API either. Read financial news or pages such as 「Yahoo奇摩股市 類股報價」 (Yahoo Taiwan stock group quotes) or 「Goodinfo 產業類別」 (Goodinfo industry categories) via web search; no scraper is needed. These page layouts may change, so if structured data is not available, read the text from web search results and judge from that.

## 5. Trading calendar / is today a trading day

TWSE publishes the market holiday dates. If no stable JSON API turns up, search the web for 「台灣證交所 {year} 開休市日期」 (TWSE trading and holiday dates for the year); checking once a year is enough.
