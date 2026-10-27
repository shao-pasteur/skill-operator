import pytest

from sharron_support import load, row

ledger = load("ledger")


def summary_block(text):
    return text.split(ledger.SUMMARY_START)[1].split(ledger.SUMMARY_END)[0]


def costs_rows(costs):
    return [row(task_id=f"t-20261027-{i:02d}", cost_usd=f"{c:.4f}") for i, c in enumerate(costs, 1)]


def test_ledger_round_trips_canonically():
    correction = {"task_id": "t-20261027-01", "date": "2026-10-28"}
    text = ledger.render_ledger(ledger.Ledger([row()], [correction]))
    parsed = ledger.parse_ledger(text)
    assert (parsed.tasks, parsed.corrections) == ([row()], [correction])
    assert ledger.render_ledger(parsed) == text


def test_summary_block_reports_n_median_and_p80():
    text = ledger.render_ledger(ledger.Ledger(costs_rows([0.1, 0.2, 0.3, 0.4, 0.5]), []))
    assert "| claude-code | research | 3 | 5 | 0.3000 | 0.4200 |" in summary_block(text)


def test_unsuccessful_tasks_are_left_out_of_the_summary():
    rows = costs_rows([0.1, 0.2, 0.3, 0.4, 0.5])
    rows[1]["outcome"] = "failed"
    rows[2]["verified"] = "2/3"
    rows[3].update(cost_usd="unknown", measurement="unknown")
    led = ledger.Ledger(rows, [{"task_id": rows[4]["task_id"], "date": "2026-10-28"}])
    assert ledger.successful_rows(led) == [rows[0]]
    assert "| claude-code | research | 3 | 1 | 0.1000 | 0.1000 |" in summary_block(ledger.render_ledger(led))


@pytest.mark.parametrize("field,value", [
    ("domain", "a|b"), ("task_id", "../x"), ("difficulty", "6"), ("verified", "4/3"),
    ("cost_usd", "-1"), ("models", "a\nb"), ("platform", "auto"), ("outcome", "ok"),
])
def test_invalid_fields_are_rejected(field, value):
    with pytest.raises(ledger.LedgerError):
        ledger.validate_task_row(row(**{field: value}))


def test_merge_keeps_rows_from_both_sides():
    upstream = ledger.render_ledger(ledger.Ledger([row(), row(task_id="t-20261027-02")], []))
    local = ledger.render_ledger(ledger.Ledger([row(), row(task_id="t-20261027-03")], []))
    merged = ledger.parse_ledger(ledger.merge_ledgers(upstream, local))
    assert [r["task_id"] for r in merged.tasks] == ["t-20261027-01", "t-20261027-02", "t-20261027-03"]


def test_trailing_newline_is_rejected_in_every_pattern_field():
    for field in ("task_id", "date", "domain", "cost_usd", "verified", "subagents"):
        with pytest.raises(ledger.LedgerError):
            ledger.validate_task_row(row(**{field: row()[field] + "\n"}))


def test_empty_models_round_trip():
    text = ledger.render_ledger(ledger.Ledger([row(models="")], []))
    assert ledger.parse_ledger(text).tasks == [row(models="")]


def test_p80_of_one_value_is_that_value():
    assert ledger.p80([0.25]) == 0.25
    assert ledger.p80([0.1, 0.2, 0.3, 0.4, 0.5]) == pytest.approx(0.42)


def test_merge_deduplicates_corrections_and_rejects_bad_text():
    c = {"task_id": "t-20261027-01", "date": "2026-10-28"}
    text = ledger.render_ledger(ledger.Ledger([row()], [c]))
    assert len(ledger.parse_ledger(ledger.merge_ledgers(text, text)).corrections) == 1
    with pytest.raises(ledger.LedgerError):
        ledger.merge_ledgers(text, "<<<<<<< HEAD\n" + text)


def test_stray_lines_inside_the_tables_are_rejected_not_dropped():
    text = ledger.render_ledger(ledger.Ledger(costs_rows([0.1, 0.2]), []))
    first, second = [line for line in text.splitlines() if line.startswith("| t-")]
    broken = text.replace(second, "=======\n" + second)
    with pytest.raises(ledger.LedgerError):
        ledger.parse_ledger(broken)
    stale = text.replace("0.1500", "9.9999")  # a stale summary is tolerated
    assert ledger.parse_ledger(stale).tasks == costs_rows([0.1, 0.2])
