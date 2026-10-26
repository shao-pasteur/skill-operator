#!/usr/bin/env python3
"""
build_report.py — assemble the Taiwan stock tracking report (Markdown + charts), compare signals
with the previous run and trigger a macOS notification when they change.

Usage:
    python3 build_report.py --input payload.json      # writes to the vault's Investing/Daily/ by default
    python3 build_report.py --input payload.json --capital 500000   # adds neutral capital math to the closing summary

Output goes straight into the Obsidian vault (Investing/Daily/{date}/). Reports carry YAML frontmatter
so Obsidian tags, graph and Dataview can find them. Report text stays in Traditional Chinese.

--capital (or capital_twd in the payload, or capital_twd in base-dir/config.json; default 500000)
is used only for the capital-math table in the close_summary phase: plain affordability arithmetic
(how much one lot costs, how many lots the capital buys), never buy/sell or allocation advice.

payload.json format:
{
  "date": "2026-07-13",
  "phase": "premarket" | "update" | "close_watch" | "close_summary",
  "time_label": "0850",
  "market_notes": ["US market highlight...", "..."], // optional, recommended for premarket
  "industries": [{"name": "...", "reason": "..."}],  // optional, recommended for premarket
  "stocks": [
    {
      "symbol": "2330",
      "name": "<stock name>",
      "industry": "<industry>",
      "closes": [880.0, 885.5, ...],   // oldest first, including today's latest price, at least 20
      "bollinger": { ... bollinger.py's result for this stock ... }
    },
    ...
  ]
}

Output (base-dir defaults to the vault's Investing/Daily):
    {base-dir}/{date}/reports/{time_label}_{phase}.md   (with Obsidian YAML frontmatter)
    {base-dir}/{date}/charts/{symbol}_bollinger.png
    {base-dir}/{date}/state/signals_state.json  (updated to this run's states)
    {base-dir}/{date}/logs/run_{time_label}.log

The script only organizes information, draws charts, compares states and notifies; it never writes
buy/sell advice. All user-facing text is deliberately neutral and technical, and ends with the disclaimer.
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Everything written into reports, charts and notifications stays in Traditional Chinese (SKILL.md rule 6).
DISCLAIMER = (
    "> 本報告僅整理公開市場資訊與布林通道等技術指標的客觀計算結果，用於個人研究參考，"
    "**不構成任何投資建議、亦非邀約買賣任何有價證券**。過往技術訊號不保證未來走勢，"
    "投資有風險，請自行判斷並承擔投資決策的風險與責任。本報告非持有證券投資顧問執照者"
    "所出具之投資分析意見。"
)

POSITION_LABEL = {
    "below_lower": "跌破下軌",
    "near_lower": "接近下軌",
    "within": "通道內（中段）",
    "near_upper": "接近上軌",
    "above_upper": "突破上軌",
}

PHASE_LABEL = {
    "premarket": "開盤前簡報",
    "update": "盤中動態更新",
    "close_watch": "收盤前賣點追蹤",
    "close_summary": "收盤總結",
}


def rolling_bands(closes, period=20, num_std=2):
    """Return (sma, upper, lower) for every close; the first period-1 entries are nan (not enough data; plots leave them blank)."""
    nan = float("nan")
    out = []
    for i in range(len(closes)):
        if i < period - 1:
            out.append((nan, nan, nan))
            continue
        window = closes[i - period + 1 : i + 1]
        sma = statistics.fmean(window)
        std = statistics.pstdev(window)
        out.append((sma, sma + num_std * std, sma - num_std * std))
    return out


def plot_chart(symbol, name, closes, chart_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        # Try the built-in macOS Chinese fonts in order so Chinese chart labels do not render as empty boxes
        for font_name in ("PingFang TC", "Heiti TC", "Arial Unicode MS", "Microsoft JhengHei"):
            if any(font_name.lower() in f.name.lower() for f in matplotlib.font_manager.fontManager.ttflist):
                matplotlib.rcParams["font.sans-serif"] = [font_name]
                matplotlib.rcParams["axes.unicode_minus"] = False
                break
    except ImportError:
        print(f"[warning] matplotlib not found; skipping the chart for {symbol} (install it with pip install matplotlib)", file=sys.stderr)
        return False

    bands = rolling_bands(closes)
    x = list(range(len(closes)))
    sma_line = [b[0] for b in bands]
    upper_line = [b[1] for b in bands]
    lower_line = [b[2] for b in bands]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(x, closes, label="收盤價", color="#1f77b4", linewidth=1.6)
    ax.plot(x, sma_line, label="20日均線", color="#888888", linewidth=1.0, linestyle="--")
    ax.plot(x, upper_line, label="上軌", color="#d62728", linewidth=1.0, linestyle=":")
    ax.plot(x, lower_line, label="下軌", color="#2ca02c", linewidth=1.0, linestyle=":")
    ax.fill_between(x, lower_line, upper_line, color="#cccccc", alpha=0.15)
    ax.set_title(f"{symbol} {name} — 布林通道")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=130)
    plt.close(fig)
    return True


def mac_notify(title, message):
    if sys.platform != "darwin":
        return
    try:
        # Pass the text as argv so quotes in news or stock names cannot run as AppleScript
        subprocess.run(
            [
                "osascript",
                "-e", "on run argv",
                "-e", 'display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"',
                "-e", "end run",
                title,
                message,
            ],
            check=False,
            timeout=5,
        )
    except Exception as e:
        print(f"[warning] macOS notification failed: {e}", file=sys.stderr)


def load_json(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_LABEL_RE = re.compile(r"^\d{4}$")
SYMBOL_RE = re.compile(r"^[0-9A-Za-z]{1,10}$")


def check_payload(payload):
    """Payload fields become file names, so check their format to avoid writing outside base_dir."""
    if not DATE_RE.match(str(payload.get("date", ""))):
        raise ValueError(f"payload.date must be YYYY-MM-DD: {payload.get('date')!r}")
    if not TIME_LABEL_RE.match(str(payload.get("time_label", ""))):
        raise ValueError(f"payload.time_label must be four digits (for example 0850): {payload.get('time_label')!r}")
    if payload.get("phase") not in PHASE_LABEL:
        raise ValueError(f"payload.phase must be one of {', '.join(PHASE_LABEL)}: {payload.get('phase')!r}")
    for stock in payload.get("stocks", []):
        if not SYMBOL_RE.match(str(stock.get("symbol", ""))):
            raise ValueError(f"invalid stock symbol: {stock.get('symbol')!r}")


def build(payload, base_dir: Path):
    check_payload(payload)
    date = payload["date"]
    phase = payload["phase"]
    time_label = payload["time_label"]

    day_dir = base_dir / date
    reports_dir = day_dir / "reports"
    charts_dir = day_dir / "charts"
    state_dir = day_dir / "state"
    logs_dir = day_dir / "logs"
    for d in (reports_dir, charts_dir, state_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    state_path = state_dir / "signals_state.json"
    prev_state = load_json(state_path)  # { symbol: {"position": ..., "price": ...} }
    new_state = {}
    changed_stocks = []

    lines = []
    # Obsidian YAML frontmatter so tags, graph and Dataview can find the report
    lines.append("---")
    lines.append(f"tags: [investing, daily-stock, {phase}]")
    lines.append(f"date: {date}")
    lines.append(f"phase: {phase}")
    lines.append(f"time: \"{time_label}\"")
    lines.append("source: tw-stock-daily-tracker")
    lines.append("---")
    lines.append("")
    lines.append(f"# 台股追蹤報告 — {date} {time_label[:2]}:{time_label[2:]}（{PHASE_LABEL.get(phase, phase)}）")
    lines.append("")
    lines.append(f"> 追蹤清單見 [[watchlist]]。完整當日總覽見 [[台股日報 {date}]]。")
    lines.append("")

    if payload.get("market_notes"):
        lines.append("## 市場背景")
        for note in payload["market_notes"]:
            lines.append(f"- {note}")
        lines.append("")

    if payload.get("industries"):
        lines.append("## 今日熱門產業與選股邏輯")
        for ind in payload["industries"]:
            lines.append(f"- **{ind.get('name')}**：{ind.get('reason', '')}")
        lines.append("")

    lines.append("## 9 檔股票技術面追蹤")
    lines.append("")

    for stock in payload.get("stocks", []):
        symbol = stock["symbol"]
        name = stock.get("name", "")
        industry = stock.get("industry", "")
        b = stock.get("bollinger", {})
        closes = stock.get("closes", [])

        position = b.get("position")
        prev = prev_state.get(symbol, {})
        prev_position = prev.get("position")
        is_changed = prev_position is not None and prev_position != position

        new_state[symbol] = {"position": position, "price": b.get("current_price")}
        if is_changed:
            changed_stocks.append(
                f"{symbol} {name}：{POSITION_LABEL.get(prev_position, prev_position)} → {POSITION_LABEL.get(position, position)}"
            )

        chart_rel = f"../charts/{symbol}_bollinger.png"
        if closes and len(closes) >= 20:
            plot_chart(symbol, name, closes, charts_dir / f"{symbol}_bollinger.png")

        lines.append(f"### {symbol} {name}（{industry}）")
        lines.append(f"- 目前價格：{b.get('current_price', 'N/A')}")
        lines.append(
            f"- 布林通道：上軌 {b.get('upper_band', 'N/A')} ／ 中軌(20MA) {b.get('sma', 'N/A')} ／ 下軌 {b.get('lower_band', 'N/A')}"
        )
        lines.append(f"- 目前位置：{POSITION_LABEL.get(position, position)}（%B: {b.get('pct_b', 'N/A')}）")
        if is_changed:
            lines.append(
                f"- ⚠️ **訊號變化**：從「{POSITION_LABEL.get(prev_position, prev_position)}」變成「{POSITION_LABEL.get(position, position)}」"
            )
        if closes and len(closes) >= 20:
            lines.append(f"- 圖表：![]({chart_rel})")
        lines.append("")

    # Capital math (neutral, not advice): only when capital is given and this is the closing summary
    capital = payload.get("capital_twd")
    if capital and phase == "close_summary":
        lines.append("## 資金試算（僅供參考，非建議買進任一檔）")
        lines.append(f"> 以下純為資金規模的可負擔性算術，本金 = 新台幣 {int(capital):,} 元。"
                     "台股 1 張 = 1000 股。**這不是買賣或配置建議**，只是讓你知道每檔一張大約多少錢、"
                     "這個本金買得起幾張，實際是否買賣請自行判斷或洽持牌投顧。")
        lines.append("")
        lines.append("| 代號 | 名稱 | 收盤價 | 一張約需 | 本金可買張數 | 一張佔本金% |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for stock in payload.get("stocks", []):
            b = stock.get("bollinger", {})
            price = b.get("current_price")
            if not price:
                continue
            per_lot = price * 1000
            lots = int(capital // per_lot)
            pct = per_lot / capital * 100
            lines.append(f"| {stock['symbol']} | {stock.get('name','')} | {price} | "
                         f"{per_lot:,.0f} | {lots} | {pct:.1f}% |")
        lines.append("")

    lines.append("## 免責聲明")
    lines.append(DISCLAIMER)
    lines.append("")

    report_text = "\n".join(lines)
    report_path = reports_dir / f"{time_label}_{phase}.md"
    report_path.write_text(report_text, encoding="utf-8")

    save_json(state_path, new_state)

    log_line = f"{datetime.now().isoformat()} phase={phase} time={time_label} stocks={len(payload.get('stocks', []))} changed={len(changed_stocks)}\n"
    (logs_dir / f"run_{time_label}.log").write_text(log_line, encoding="utf-8")

    if changed_stocks:
        summary = "；".join(changed_stocks[:3])
        if len(changed_stocks) > 3:
            summary += f" 等共 {len(changed_stocks)} 檔"
        mac_notify("台股訊號變化", summary)

    return report_path, changed_stocks


def main():
    parser = argparse.ArgumentParser(description="Assemble the Taiwan stock tracking report and compare signal changes")
    parser.add_argument("--input", "-i", required=True, help="input payload JSON file")
    # Path of the Investing folder in the Obsidian vault, provided by the user as an environment variable
    VAULT_INVESTING = os.environ.get("TW_STOCK_INVESTING_DIR")
    if VAULT_INVESTING:
        # Paths with spaces are usually quoted, which stops the shell from expanding "~"
        VAULT_INVESTING = os.path.expanduser(VAULT_INVESTING)
    parser.add_argument(
        "--base-dir",
        "-b",
        default=f"{VAULT_INVESTING}/Daily" if VAULT_INVESTING else None,
        help="output root (default $TW_STOCK_INVESTING_DIR/Daily; one {date} subfolder per day)",
    )
    parser.add_argument(
        "--config",
        default=f"{VAULT_INVESTING}/config.json" if VAULT_INVESTING else None,
        help="settings file (default $TW_STOCK_INVESTING_DIR/config.json) for capital_twd and other shared settings",
    )
    parser.add_argument(
        "--capital",
        type=int,
        default=None,
        help="capital in New Taiwan dollars for the neutral capital math in the closing summary. Defaults to "
             "capital_twd in config.json, then 500000. Used only for affordability arithmetic, never advice.",
    )
    args = parser.parse_args()
    if args.base_dir is None or args.config is None:
        parser.error("set the TW_STOCK_INVESTING_DIR environment variable (the Investing folder in your Obsidian vault), or pass --base-dir and --config")

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Capital precedence: --capital > payload.capital_twd > config.json > default 500000
    if "capital_twd" not in payload:
        capital = args.capital
        if capital is None:
            cfg = load_json(Path(args.config).expanduser())
            capital = cfg.get("capital_twd", 500000)
        payload["capital_twd"] = capital
    elif args.capital is not None:
        payload["capital_twd"] = args.capital

    try:
        report_path, changed = build(payload, Path(args.base_dir).expanduser())
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Report written: {report_path}")
    if changed:
        print("Signal changes:")
        for c in changed:
            print(f"  - {c}")
    else:
        print("No signal changes this run.")


if __name__ == "__main__":
    main()
