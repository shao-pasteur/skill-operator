import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/finance/skills/tw-stock-vault-sync/scripts/sync.py"
TRACKER = ROOT / "plugins/finance/skills/tw-stock-daily-tracker"

INVESTING_MD = """---
tags: [investing]
---

# Investing

自己寫的說明，同步不會動到這段。

## 最近交易日
<!-- sync:recent:start -->
<!-- sync:recent:end -->

## 個股
<!-- sync:stocks:start -->
舊內容
<!-- sync:stocks:end -->

## 產業
<!-- sync:industries:start -->
<!-- sync:industries:end -->

結尾的筆記。
"""

CONFIG = {
    "capital_twd": 500000,
    "fixed_industries": [
        {"name": "記憶體", "stocks": [{"symbol": "2408", "name": "南亞科"}]},
        {"name": "航海", "stocks": [{"symbol": "2603", "name": "長榮"}]},
    ],
}

SELECTED = {
    "date": "2026-11-14",
    "dynamic_industries": [
        {"name": "記憶體", "reason": "美光財報優於預期"},
        {"name": "軍工/無人機", "reason": "無人機條例 | 政策題材"},
        {"name": "航運", "reason": "紅海航線運價上漲"},
    ],
    "fixed_industries": ["記憶體", "航海"],
    "stocks": [
        {"symbol": "2408", "name": "南亞科", "industry": "記憶體", "source": "dynamic", "also_fixed": True},
        {"symbol": "2634", "name": "漢翔", "industry": "軍工/無人機", "source": "dynamic"},
        {"symbol": "2603", "name": "長榮", "industry": "航運", "source": "dynamic", "also_fixed": True},
    ],
}

SIGNALS = {
    "2408": {"position": "near_lower", "price": 52.3},
    "2634": {"position": "within", "price": 61.0},
    "2603": {"position": "above_upper", "price": 210.5},
}


@pytest.fixture
def sync():
    spec = importlib.util.spec_from_file_location("tw_stock_vault_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def investing(tmp_path):
    root = tmp_path / "Investing"
    root.mkdir()
    (root / "Investing.md").write_text(INVESTING_MD, encoding="utf-8")
    (root / "config.json").write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    return root


def make_day(root, date, selected=SELECTED, signals=SIGNALS, summary=True, overview=None):
    day = root / "Daily" / date
    (day / "state").mkdir(parents=True)
    (day / "reports").mkdir()
    (day / "state/selected_stocks.json").write_text(
        json.dumps({**selected, "date": date}, ensure_ascii=False), encoding="utf-8")
    (day / "state/signals_state.json").write_text(json.dumps(signals), encoding="utf-8")
    if summary:
        (day / "reports/summary_close.md").write_text("# 收盤總結\n", encoding="utf-8")
    if overview is not None:
        (day / f"台股日報 {date}.md").write_text(overview, encoding="utf-8")
    return day


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def section(text, name):
    start, end = f"<!-- sync:{name}:start -->", f"<!-- sync:{name}:end -->"
    return text[text.index(start) + len(start):text.index(end)].strip()


def outside_markers(text):
    return re.sub(r"(<!-- sync:\w+:start -->).*?(<!-- sync:\w+:end -->)", r"\1\2", text, flags=re.S)


def test_missing_summary_close_writes_nothing(sync, investing, capsys):
    make_day(investing, "2026-11-14", summary=False)
    before = snapshot(investing)
    assert sync.main(["--date", "2026-11-14", "--investing-dir", str(investing)]) == 2
    assert snapshot(investing) == before
    assert not (investing / "Stocks").exists() and not (investing / "Industries").exists()
    assert "收盤分析還沒跑" in capsys.readouterr().err


def test_missing_state_file_writes_nothing(sync, investing):
    day = make_day(investing, "2026-11-14")
    (day / "state/signals_state.json").unlink()
    before = snapshot(investing)
    assert sync.main(["--date", "2026-11-14", "--investing-dir", str(investing)]) == 2
    assert snapshot(investing) == before


def test_rerun_is_byte_identical(sync, investing):
    make_day(investing, "2026-11-13", overview="# 台股日報\n\n**一句話總結**：大盤小漲。\n")
    make_day(investing, "2026-11-14")
    assert sync.main(["--date", "2026-11-13", "--investing-dir", str(investing)]) == 0
    assert sync.main(["--date", "2026-11-14", "--investing-dir", str(investing)]) == 0
    first = snapshot(investing)
    assert sync.main(["--date", "2026-11-14", "--investing-dir", str(investing)]) == 0
    assert snapshot(investing) == first
    for path, data in first.items():
        if path.suffix == ".md":
            assert data.endswith(b"\n") and not data.endswith(b"\n\n\n")


def test_rerun_with_changed_data_replaces_the_row(sync, investing):
    make_day(investing, "2026-11-13")
    day = make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-13")
    sync.run(investing, "2026-11-14")
    changed = {**SIGNALS, "2408": {"position": "below_lower", "price": 49.8}}
    (day / "state/signals_state.json").write_text(json.dumps(changed), encoding="utf-8")
    assert sync.run(investing, "2026-11-14")[0] == 0

    page = (investing / "Stocks/2408 南亞科.md").read_text(encoding="utf-8")
    rows = [line for line in section(page, "signals").splitlines() if line.startswith("| 2026")]
    assert rows == [
        "| 2026-11-14 | 49.8 | 跌破下軌 | [[記憶體]] |",
        "| 2026-11-13 | 52.3 | 接近下軌 | [[記憶體]] |",
    ]
    overview = (investing / "Investing.md").read_text(encoding="utf-8")
    assert "| [[2408 南亞科]] | 49.8 | 跌破下軌 | 2026-11-14 |" in section(overview, "stocks")


def test_stock_page_layout(sync, investing):
    make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-14")
    page = (investing / "Stocks/2634 漢翔.md").read_text(encoding="utf-8")
    assert page.startswith('---\ntags: [investing, stock]\nsymbol: "2634"\nname: "漢翔"\n---\n\n# 2634 漢翔\n')
    assert "← 回到 [[Investing]]" in page
    assert "| 日期 | 收盤價 | 通道位置 | 當天所屬產業 |" in page
    assert page.rstrip("\n").endswith(sync.DISCLAIMER)


def test_stock_in_two_industries_lists_both(sync, investing):
    selected = {**SELECTED, "stocks": SELECTED["stocks"] + [
        {"symbol": "2408", "name": "南亞科", "industry": "AI伺服器", "source": "dynamic"}]}
    make_day(investing, "2026-11-14", selected=selected)
    sync.run(investing, "2026-11-14")
    page = (investing / "Stocks/2408 南亞科.md").read_text(encoding="utf-8")
    assert "| 2026-11-14 | 52.3 | 接近下軌 | [[記憶體]]、[[AI伺服器]] |" in page


def test_dynamic_and_fixed_industries_both_listed(sync, investing):
    selected = {**SELECTED, "stocks": [
        {"symbol": "2408", "name": "南亞科", "industry": "AI伺服器", "source": "dynamic", "also_fixed": True}]}
    make_day(investing, "2026-11-14", selected=selected)
    sync.run(investing, "2026-11-14")
    page = (investing / "Stocks/2408 南亞科.md").read_text(encoding="utf-8")
    assert "| [[AI伺服器]]、[[記憶體]] |" in page


def test_alias_maps_shipping_to_the_fixed_name(sync, investing):
    make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-14")
    assert (investing / "Industries/航海.md").exists()
    assert not (investing / "Industries/航運.md").exists()
    stock = (investing / "Stocks/2603 長榮.md").read_text(encoding="utf-8")
    assert "| 2026-11-14 | 210.5 | 突破上軌 | [[航海]] |" in stock
    industry = (investing / "Industries/航海.md").read_text(encoding="utf-8")
    assert "| 2026-11-14 | 紅海航線運價上漲 | [[2603 長榮]] |" in industry


def test_alias_comes_from_config(sync, investing):
    config = {**CONFIG, "industry_aliases": {"記憶體": "記憶體IC"}}
    (investing / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-14")
    assert (investing / "Industries/記憶體IC.md").exists()
    assert (investing / "Industries/航運.md").exists()  # the default alias is replaced, not merged


def test_slash_in_industry_name(sync, investing):
    make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-14")
    path = investing / "Industries/軍工・無人機.md"
    assert path.exists()
    page = path.read_text(encoding="utf-8")
    assert "| 2026-11-14 | 無人機條例 \\| 政策題材 | [[2634 漢翔]] |" in page
    assert "tags: [investing, industry]" in page and "<!-- sync:news:start -->" in page
    stock = (investing / "Stocks/2634 漢翔.md").read_text(encoding="utf-8")
    assert "[[軍工・無人機]]" in stock
    overview = (investing / "Investing.md").read_text(encoding="utf-8")
    assert "| [[軍工・無人機]] | 2026-11-14 | 1 |" in section(overview, "industries")


def test_only_hot_industries_get_pages(sync, investing):
    selected = {**SELECTED, "dynamic_industries": SELECTED["dynamic_industries"][1:]}
    make_day(investing, "2026-11-14", selected=selected)
    sync.run(investing, "2026-11-14")
    assert not (investing / "Industries/記憶體.md").exists()
    assert "[[記憶體]]" in (investing / "Stocks/2408 南亞科.md").read_text(encoding="utf-8")


def test_investing_sections(sync, investing):
    for d in ("2026-11-07", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"):
        make_day(investing, d)
    no_memory = {**SELECTED, "dynamic_industries": SELECTED["dynamic_industries"][1:]}
    make_day(investing, "2026-11-14", selected=no_memory, overview=(
        "---\ntags: [investing, daily-stock]\ndate: 2026-11-14\n---\n\n# 台股日報 2026-11-14\n\n"
        "> **一句話總結**：記憶體與航運走強，軍工持平。\n\n| 代號 | 名稱 |\n|---|---|\n"))
    make_day(investing, "2026-11-15", summary=False)
    sync.run(investing, "2026-11-13")
    assert sync.run(investing, "2026-11-14")[0] == 0
    text = (investing / "Investing.md").read_text(encoding="utf-8")

    assert section(text, "recent") == "\n".join([
        "| 日期 | 一句話 |",
        "|---|---|",
        "| [[台股日報 2026-11-14\\|2026-11-14]] | 記憶體與航運走強，軍工持平。 |",
        "| 2026-11-13 | — |",
        "| 2026-11-12 | — |",
        "| 2026-11-11 | — |",
        "| 2026-11-10 | — |",
    ])
    assert section(text, "stocks") == "\n".join([
        "| 個股 | 最新收盤 | 通道位置 | 最後更新 |",
        "|---|---|---|---|",
        "| [[2408 南亞科]] | 52.3 | 接近下軌 | 2026-11-14 |",
        "| [[2603 長榮]] | 210.5 | 突破上軌 | 2026-11-14 |",
        "| [[2634 漢翔]] | 61 | 通道內（中段） | 2026-11-14 |",
    ])
    assert section(text, "industries") == "\n".join([
        "| 產業 | 最近熱門日期 | 熱門次數 |",
        "|---|---|---|",
        "| [[航海]] | 2026-11-14 | 2 |",
        "| [[軍工・無人機]] | 2026-11-14 | 2 |",
        "| [[記憶體]] | 2026-11-13 | 1 |",
    ])
    assert outside_markers(text) == outside_markers(INVESTING_MD)


@pytest.mark.parametrize("marker", ["<!-- sync:stocks:end -->", "<!-- sync:industries:start -->"])
def test_missing_investing_markers_leave_it_untouched(sync, investing, capsys, marker):
    original = INVESTING_MD.replace(marker, "")
    (investing / "Investing.md").write_text(original, encoding="utf-8")
    make_day(investing, "2026-11-14")
    assert sync.main(["--date", "2026-11-14", "--investing-dir", str(investing)]) == 3
    assert (investing / "Investing.md").read_text(encoding="utf-8") == original
    assert marker in capsys.readouterr().err
    assert (investing / "Stocks/2408 南亞科.md").exists()
    assert (investing / "Industries/航海.md").exists()


def test_missing_investing_md(sync, investing):
    (investing / "Investing.md").unlink()
    make_day(investing, "2026-11-14")
    assert sync.run(investing, "2026-11-14")[0] == 3
    assert not (investing / "Investing.md").exists()
    assert (investing / "Stocks/2408 南亞科.md").exists()


def test_user_text_on_a_page_is_kept(sync, investing):
    make_day(investing, "2026-11-13")
    make_day(investing, "2026-11-14")
    sync.run(investing, "2026-11-13")
    path = investing / "Stocks/2408 南亞科.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "← 回到 [[Investing]]\n", "← 回到 [[Investing]]\n\n我的筆記。\n"), encoding="utf-8")
    sync.run(investing, "2026-11-14")
    page = path.read_text(encoding="utf-8")
    assert "我的筆記。" in page and "| 2026-11-14 |" in page and "| 2026-11-13 |" in page


def test_one_liner_formats(sync, tmp_path):
    cases = {
        "# 台股日報\n\n**一句話總結**：大盤收高。\n": "大盤收高。",
        "# 台股日報\n\n## 一句話總結\n\n> 記憶體走強。\n": "記憶體走強。",
        "---\ndate: x\n---\n# 台股日報\n\n今天航運領漲。\n\n## 表格\n": "今天航運領漲。",
        "# 台股日報\n\n| a |\n|---|\n": None,
    }
    for i, (text, expected) in enumerate(cases.items()):
        path = tmp_path / f"{i}.md"
        path.write_text(text, encoding="utf-8")
        assert sync.one_liner(path) == expected


def test_env_var_and_bad_date(sync, investing, monkeypatch):
    make_day(investing, "2026-11-14")
    monkeypatch.setenv("TW_STOCK_INVESTING_DIR", str(investing))
    assert sync.main(["--date", "2026-11-14"]) == 0
    assert sync.main(["--date", "../x"]) == 1
    monkeypatch.delenv("TW_STOCK_INVESTING_DIR")
    assert sync.main(["--date", "2026-11-14"]) == 1


def test_labels_and_disclaimer_match_the_tracker(sync):
    skill = (TRACKER / "SKILL.md").read_text(encoding="utf-8")
    assert sync.DISCLAIMER in skill
    spec = importlib.util.spec_from_file_location("build_report", TRACKER / "scripts/build_report.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    assert sync.POSITION_LABEL == report.POSITION_LABEL
    assert sync.DISCLAIMER == report.DISCLAIMER
