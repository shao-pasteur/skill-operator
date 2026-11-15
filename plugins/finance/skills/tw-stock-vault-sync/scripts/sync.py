#!/usr/bin/env python3
"""
sync.py — copy one trading day's tw-stock-daily-tracker results into the Obsidian Investing folder.

Usage:
    python3 sync.py                         # today (Asia/Taipei), folder from $TW_STOCK_INVESTING_DIR
    python3 sync.py --date 2026-11-14
    python3 sync.py --date 2026-11-14 --investing-dir "/path/to/vault/Investing"

Reads (written by tw-stock-daily-tracker):
    {investing}/config.json                              optional: industry_aliases, fixed_industries
    {investing}/Daily/{date}/reports/summary_close.md    must exist (the close has been analyzed)
    {investing}/Daily/{date}/state/selected_stocks.json
    {investing}/Daily/{date}/state/signals_state.json
    {investing}/Daily/{date}/台股日報 {date}.md            optional: the one-sentence summary

Writes (only the tables between sync markers; everything else in a page is left alone):
    {investing}/Stocks/{symbol} {name}.md     one row per date: close, band position, industries
    {investing}/Industries/{industry}.md      one row per date the industry was hot: reason, stocks
    {investing}/Investing.md                  recent days, stock overview, industry overview

Exit codes:
    0  synced
    1  bad arguments or unreadable input
    2  the day is not ready (summary_close.md or a state file is missing); nothing written
    3  Investing.md or some of its markers are missing; Investing.md left untouched,
       stock and industry pages still written

Running it twice for the same date leaves every file byte-identical. Python 3 standard library only.
Every text written into the vault is in Traditional Chinese.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Copied word for word from tw-stock-daily-tracker's SKILL.md ("Disclaimer").
DISCLAIMER = (
    "> 本報告僅整理公開市場資訊與布林通道等技術指標的客觀計算結果，用於個人研究參考，"
    "**不構成任何投資建議、亦非邀約買賣任何有價證券**。過往技術訊號不保證未來走勢，"
    "投資有風險，請自行判斷並承擔投資決策的風險與責任。本報告非持有證券投資顧問執照者"
    "所出具之投資分析意見。"
)

# Same labels as tw-stock-daily-tracker's build_report.py.
POSITION_LABEL = {
    "below_lower": "跌破下軌",
    "near_lower": "接近下軌",
    "within": "通道內（中段）",
    "near_upper": "接近上軌",
    "above_upper": "突破上軌",
}

DEFAULT_ALIASES = {"航運": "航海"}
RECENT_DAYS = 5
EMPTY = "—"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SYMBOL_RE = re.compile(r"^[0-9A-Za-z]{1,10}$")
ROW_DATE_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|")
# Characters Obsidian does not allow in file names or that break wikilinks.
UNSAFE_NAME_RE = re.compile(r'[/\\:*?"<>|#^\[\]]')
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

STOCK_MARKERS = ("<!-- sync:signals:start -->", "<!-- sync:signals:end -->")
INDUSTRY_MARKERS = ("<!-- sync:news:start -->", "<!-- sync:news:end -->")
INVESTING_SECTIONS = ("recent", "stocks", "industries")

STOCK_HEADER = ["日期", "收盤價", "通道位置", "當天所屬產業"]
INDUSTRY_HEADER = ["日期", "消息", "影響個股"]


class NotReady(Exception):
    pass


# ---------- small helpers ----------

def today_taipei():
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Taipei")
    except Exception:  # no tz database: Taiwan has no daylight saving time
        tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d")


def cell(text):
    """Make text safe inside a Markdown table cell."""
    text = " ".join(str(text).split())
    return text.replace("|", "\\|") if text else EMPTY


def safe_name(name):
    return UNSAFE_NAME_RE.sub("・", " ".join(str(name).split()))


def format_price(price):
    if isinstance(price, bool) or price is None:
        return EMPTY
    if isinstance(price, (int, float)):
        return f"{price:.2f}".rstrip("0").rstrip(".")
    return cell(price)


def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += rows
    return "\n".join(lines)


def row(cells):
    return "| " + " | ".join(cells) + " |"


def split_cells(line):
    parts = CELL_SPLIT_RE.split(line.strip())
    return [p.strip() for p in parts[1:-1]]


def read_text(path):
    return path.read_text(encoding="utf-8")


def write_text(path, text, changes):
    if not text.endswith("\n"):
        text += "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    changes.append(("新增" if old is None else "更新", path))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_block(text, markers):
    """Return (start, end) of the text between the markers, or None."""
    start_marker, end_marker = markers
    s = text.find(start_marker)
    if s < 0:
        return None
    s += len(start_marker)
    e = text.find(end_marker, s)
    if e < 0:
        return None
    return s, e


def replace_block(text, markers, body):
    s, e = find_block(text, markers)
    return text[:s] + "\n" + body + "\n" + text[e:]


def table_rows(text, markers):
    """Data rows (lines starting with a date) between the markers."""
    block = find_block(text, markers)
    if block is None:
        return []
    rows = []
    for line in text[block[0]:block[1]].splitlines():
        if ROW_DATE_RE.match(line.strip()):
            rows.append(line.strip())
    return rows


def upsert_row(page_text, markers, header, date, new_row):
    rows = [r for r in table_rows(page_text, markers) if ROW_DATE_RE.match(r).group(1) != date]
    rows.append(new_row)
    rows.sort(key=lambda r: ROW_DATE_RE.match(r).group(1), reverse=True)
    body = table(header, rows)
    if find_block(page_text, markers) is None:
        # Page exists but its markers were removed: put the table back before the disclaimer.
        block = f"{markers[0]}\n{body}\n{markers[1]}\n"
        anchor = page_text.find("## 免責聲明")
        if anchor < 0:
            return page_text.rstrip("\n") + "\n\n" + block
        return page_text[:anchor] + block + "\n" + page_text[anchor:]
    return replace_block(page_text, markers, body)


def new_page(frontmatter, title, markers, header):
    lines = ["---"]
    lines += frontmatter
    lines += [
        "---",
        "",
        f"# {title}",
        "",
        "← 回到 [[Investing]]",
        "",
        markers[0],
        table(header, []),
        markers[1],
        "",
        "## 免責聲明",
        DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


# ---------- reading the day ----------

def load_config(investing):
    path = investing / "config.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"config.json 無法讀取：{e}")


def day_ready(day_dir):
    return all((day_dir / p).is_file() for p in (
        "reports/summary_close.md", "state/selected_stocks.json", "state/signals_state.json"))


def collect_day(investing, date, config):
    day_dir = investing / "Daily" / date
    if not day_ready(day_dir):
        raise NotReady(f"{date} 的收盤分析還沒跑（缺少 reports/summary_close.md 或 state/ 裡的 JSON），無法同步。")
    try:
        selected = load_json(day_dir / "state/selected_stocks.json")
        signals = load_json(day_dir / "state/signals_state.json")
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{date} 的 state 檔案無法讀取：{e}")

    aliases = config.get("industry_aliases")
    if not isinstance(aliases, dict):
        aliases = DEFAULT_ALIASES

    def norm(name):
        name = " ".join(str(name).split())
        return aliases.get(name, name)

    day_fixed = {norm(n) for n in selected.get("fixed_industries", []) or []}
    fixed_members = {}  # symbol -> [fixed industry names, config order]
    for ind in config.get("fixed_industries", []) or []:
        name = norm(ind.get("name", ""))
        if not name or (day_fixed and name not in day_fixed):
            continue
        for s in ind.get("stocks", []) or []:
            fixed_members.setdefault(str(s.get("symbol", "")), []).append(name)

    stocks = {}  # symbol -> {"name", "industries": [..]}, in selected_stocks order
    for s in selected.get("stocks", []) or []:
        symbol = str(s.get("symbol", ""))
        if not SYMBOL_RE.match(symbol):
            print(f"[略過] 代號格式不正確：{symbol!r}", file=sys.stderr)
            continue
        entry = stocks.setdefault(symbol, {"name": str(s.get("name", "")).strip(), "industries": []})
        names = [norm(s["industry"])] if s.get("industry") else []
        if s.get("source") == "fixed" or s.get("also_fixed"):
            names += fixed_members.get(symbol, [])
        for n in names:
            if n and n not in entry["industries"]:
                entry["industries"].append(n)

    hot = {}  # industry -> reason, in dynamic_industries order
    for ind in selected.get("dynamic_industries", []) or []:
        name = norm(ind.get("name", ""))
        reason = " ".join(str(ind.get("reason", "") or "").split())
        if not name or not reason:
            continue
        hot[name] = f"{hot[name]}；{reason}" if name in hot else reason

    return stocks, hot, signals


# ---------- pages ----------

def stock_page_path(stocks_dir, symbol, name):
    if stocks_dir.is_dir():
        for p in sorted(stocks_dir.glob(f"{symbol} *.md")):
            return p
        p = stocks_dir / f"{symbol}.md"
        if p.exists():
            return p
    stem = f"{symbol} {safe_name(name)}" if name else symbol
    return stocks_dir / f"{stem}.md"


def sync_pages(investing, date, stocks, hot, signals, changes):
    stocks_dir = investing / "Stocks"
    industries_dir = investing / "Industries"

    stock_links = {}
    for symbol, info in stocks.items():
        stock_links[symbol] = stock_page_path(stocks_dir, symbol, info["name"]).stem

    for symbol, info in stocks.items():
        path = stocks_dir / f"{stock_links[symbol]}.md"
        state = signals.get(symbol) or {}
        position = state.get("position")
        label = POSITION_LABEL.get(position, position) if position else EMPTY
        industries = "、".join(f"[[{safe_name(n)}]]" for n in info["industries"]) or EMPTY
        new_row = row([date, format_price(state.get("price")), cell(label), industries])
        if path.exists():
            text = read_text(path)
        else:
            title = f"{symbol} {info['name']}".strip()
            text = new_page(
                ["tags: [investing, stock]",
                 f"symbol: {json.dumps(symbol)}",
                 f"name: {json.dumps(info['name'], ensure_ascii=False)}"],
                title, STOCK_MARKERS, STOCK_HEADER)
        write_text(path, upsert_row(text, STOCK_MARKERS, STOCK_HEADER, date, new_row), changes)

    for name, reason in hot.items():
        path = industries_dir / f"{safe_name(name)}.md"
        members = [f"[[{stock_links[s]}]]" for s, info in stocks.items() if name in info["industries"]]
        new_row = row([date, cell(reason), "、".join(members) or EMPTY])
        if path.exists():
            text = read_text(path)
        else:
            text = new_page(
                ["tags: [investing, industry]",
                 f"industry: {json.dumps(name, ensure_ascii=False)}"],
                name, INDUSTRY_MARKERS, INDUSTRY_HEADER)
        write_text(path, upsert_row(text, INDUSTRY_MARKERS, INDUSTRY_HEADER, date, new_row), changes)


# ---------- Investing.md ----------

def strip_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            return text[end + 4:]
    return text


SUMMARY_LABEL_RE = re.compile(r"^(?:>\s*)?(?:[-*]\s+)?\**\s*一句話[^：:]{0,8}[：:]\s*\**\s*(.+)$")


def one_liner(path):
    """The one-sentence summary of a 台股日報 page, or None."""
    if not path.is_file():
        return None
    lines = strip_frontmatter(read_text(path)).splitlines()

    def clean(line):
        line = re.sub(r"^(?:>\s*)+", "", line.strip())
        line = re.sub(r"^[-*]\s+", "", line).strip()
        if line.count("**") % 2:  # drop a bold marker left over from the label
            line = line[2:] if line.startswith("**") else line[:-2] if line.endswith("**") else line
        return line.strip()

    # 1. A labeled line such as 「**一句話總結**：…」
    for line in lines:
        m = SUMMARY_LABEL_RE.match(line.strip())
        if m and clean(m.group(1)):
            return clean(m.group(1))
    # 2. A heading such as 「## 一句話總結」: the first text line below it
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") and "一句話" in line:
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("#"):
                    break
                if clean(nxt):
                    return clean(nxt)
    # 3. The first paragraph line after the title
    seen_title = False
    for line in lines:
        s = line.strip()
        if s.startswith("# "):
            seen_title = True
            continue
        if not seen_title or not s:
            continue
        if s.startswith(("#", "|", "!", "<!--", "←", "---")):
            continue
        text = clean(s)
        if text and not text.startswith("←"):
            return text
    return None


def recent_section(investing):
    daily = investing / "Daily"
    dates = []
    if daily.is_dir():
        dates = sorted((p.name for p in daily.iterdir()
                        if p.is_dir() and DATE_RE.match(p.name) and day_ready(p)), reverse=True)
    rows = []
    for d in dates[:RECENT_DAYS]:
        overview = daily / d / f"台股日報 {d}.md"
        link = f"[[台股日報 {d}\\|{d}]]" if overview.is_file() else d
        rows.append(row([link, cell(one_liner(overview) or "")]))
    return table(["日期", "一句話"], rows)


def page_rows(path, markers):
    rows = table_rows(read_text(path), markers)
    return [split_cells(r) for r in rows]


def stocks_section(investing):
    entries = []
    stocks_dir = investing / "Stocks"
    for path in sorted(stocks_dir.glob("*.md")) if stocks_dir.is_dir() else []:
        rows = page_rows(path, STOCK_MARKERS)
        newest = (rows[0] if rows else []) + [EMPTY] * 3
        date, price, position = newest[0], newest[1], newest[2]
        symbol = path.stem.split(" ", 1)[0]
        entries.append((symbol, path.stem, row([f"[[{path.stem}]]", price, position, date])))
    entries.sort(key=lambda e: (e[0], e[1]))
    return table(["個股", "最新收盤", "通道位置", "最後更新"], [e[2] for e in entries])


def industries_section(investing):
    entries = []
    industries_dir = investing / "Industries"
    for path in sorted(industries_dir.glob("*.md")) if industries_dir.is_dir() else []:
        rows = page_rows(path, INDUSTRY_MARKERS)
        latest = rows[0][0] if rows else ""
        entries.append((latest, path.stem, row([f"[[{path.stem}]]", latest or EMPTY, str(len(rows))])))
    # Most recent date first; ties by name
    entries.sort(key=lambda e: e[1])
    entries.sort(key=lambda e: e[0], reverse=True)
    return table(["產業", "最近熱門日期", "熱門次數"], [e[2] for e in entries])


def investing_markers(section):
    return (f"<!-- sync:{section}:start -->", f"<!-- sync:{section}:end -->")


def sync_investing(investing, changes):
    """Return a list of problems; empty when Investing.md was synced."""
    path = investing / "Investing.md"
    if not path.is_file():
        return [f"找不到 {path.name}，未更新總覽頁。請先建立 Investing.md 並放入同步標記。"]
    text = read_text(path)
    missing = []
    for section in INVESTING_SECTIONS:
        start, end = investing_markers(section)
        if find_block(text, (start, end)) is None:
            missing += [m for m in (start, end) if m not in text] or [f"{start} … {end}（順序不對）"]
    if missing:
        return ["Investing.md 缺少以下同步標記，未修改這個檔案："] + [f"  {m}" for m in missing]
    builders = {"recent": recent_section, "stocks": stocks_section, "industries": industries_section}
    for section in INVESTING_SECTIONS:
        text = replace_block(text, investing_markers(section), builders[section](investing))
    write_text(path, text, changes)
    return []


# ---------- main ----------

def run(investing, date):
    """Sync one date. Returns (exit_code, changes, messages)."""
    changes = []
    if not DATE_RE.match(date):
        return 1, changes, [f"日期格式要是 YYYY-MM-DD：{date!r}"]
    if not investing.is_dir():
        return 1, changes, [f"找不到 Investing 資料夾：{investing}"]
    try:
        config = load_config(investing)
        stocks, hot, signals = collect_day(investing, date, config)
    except NotReady as e:
        return 2, changes, [str(e)]
    except ValueError as e:
        return 1, changes, [str(e)]
    sync_pages(investing, date, stocks, hot, signals, changes)
    problems = sync_investing(investing, changes)
    return (3 if problems else 0), changes, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync one trading day of tw-stock-daily-tracker results into the Investing folder")
    parser.add_argument("--date", default=None, help="trading day YYYY-MM-DD (default: today in Asia/Taipei)")
    parser.add_argument("--investing-dir", default=None,
                        help="the vault's Investing folder (default: $TW_STOCK_INVESTING_DIR)")
    args = parser.parse_args(argv)

    folder = args.investing_dir or os.environ.get("TW_STOCK_INVESTING_DIR")
    if not folder:
        print("沒有設定 TW_STOCK_INVESTING_DIR，請用 --investing-dir 指定 Investing 資料夾。", file=sys.stderr)
        return 1
    investing = Path(os.path.expanduser(folder))
    date = args.date or today_taipei()

    code, changes, messages = run(investing, date)
    for m in messages:
        print(m, file=sys.stderr if code else sys.stdout)
    if code in (0, 3):
        if changes:
            print(f"{date} 同步完成，變更 {len(changes)} 個檔案：")
            for kind, path in changes:
                print(f"  {kind}：{path.relative_to(investing)}")
        else:
            print(f"{date} 同步完成，所有檔案都已是最新，沒有變更。")
    return code


if __name__ == "__main__":
    sys.exit(main())
