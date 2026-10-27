import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest

from sharron_support import git, load, make_clone, make_skill, row

ledger = load("ledger")
finance = load("finance")


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

SINCE = datetime.fromisoformat("2026-10-27T10:00:00+08:00")
DEFAULTS = {"1": 0.2, "2": 0.5, "3": 1.5, "4": 4.0, "5": 10.0}
FAKE_PRICES = '[prices]\n"claude-opus-5-5" = { input = 1.0, output = 2.0, cache_write = 3.0, cache_read = 4.0 }\n'
RECORD = ["record", "--task-id", "t-20261027-01", "--since", "2026-10-27T10:00:00+08:00", "--playbook", "research",
          "--domain", "finance", "--difficulty", "3", "--subagents", "1", "--outcome", "done", "--verified", "2/2"]


def line(ts, model="claude-opus-5-5", mid="m1", rid="r1", i=10, o=5, cw=100, cr=1000):
    return json.dumps({"type": "assistant", "timestamp": ts, "requestId": rid, "message": {
        "id": mid, "model": model, "content": [{"type": "text", "text": "secret-text-123"}],
        "usage": {"input_tokens": i, "output_tokens": o,
                  "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}}})


def write_transcripts(claude, session, main, agents=None, folder="-ws"):
    base = claude / "projects" / folder
    (base / session / "subagents").mkdir(parents=True, exist_ok=True)
    (base / f"{session}.jsonl").write_text("\n".join(main) + "\n")
    for agent_id, lines in (agents or {}).items():
        (base / session / "subagents" / f"agent-{agent_id}.jsonl").write_text("\n".join(lines) + "\n")
    return base


def usage_of(claude, **kw):
    return finance.sum_usage(finance.transcript_files(claude, "s1", Path("/nowhere"), **kw), since=SINCE)


def ledger_of(pairs, **changes):
    return ledger.Ledger([row(task_id=f"t-20261027-{i:02d}", difficulty=str(d), cost_usd=f"{c:.4f}", **changes)
                          for i, (d, c) in enumerate(pairs, 1)], [])


def run_main(capsys, *args):
    code = finance.main(list(args))
    out = capsys.readouterr()
    return code, (json.loads(out.out) if out.out.strip() else None), out.err


def use_claude(monkeypatch, claude):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")


def test_usage_sums_main_and_subagents_from_the_start_time(tmp_path):
    write_transcripts(tmp_path, "s1", [line("2026-10-27T01:59:00Z", mid="m0"), line("2026-10-27T02:30:00Z")],
                      {"a1": [line("2026-10-27T03:00:00Z", model="claude-haiku-5-5", mid="m2")]})
    assert usage_of(tmp_path) == {"claude-opus-5-5": finance.ModelUsage(10, 5, 100, 1000),
                                  "claude-haiku-5-5": finance.ModelUsage(10, 5, 100, 1000)}


def test_usage_counts_each_message_once(tmp_path):
    same = line("2026-10-27T02:30:00Z", mid="m1", rid="r1")
    write_transcripts(tmp_path, "s1", [same, same, line("2026-10-27T02:31:00Z", mid="m2", rid="r2")])
    assert usage_of(tmp_path)["claude-opus-5-5"].input == 20


def test_half_written_last_line_is_skipped(tmp_path):
    write_transcripts(tmp_path, "s1", [line("2026-10-27T02:30:00Z"), '{"type": "assistant", "mess'])
    assert usage_of(tmp_path)["claude-opus-5-5"].input == 10


def test_agent_filters(tmp_path):
    write_transcripts(tmp_path, "s1", [line("2026-10-27T02:30:00Z")],
                      {"a1": [line("2026-10-27T02:30:00Z")], "a2": [line("2026-10-27T02:30:00Z")]}, folder="-any")

    def names(**kw):
        return sorted(p.name for p in finance.transcript_files(tmp_path, "s1", Path("/nowhere"), **kw))
    assert names() == ["agent-a1.jsonl", "agent-a2.jsonl", "s1.jsonl"]
    assert names(agents=frozenset({"a1"})) == ["agent-a1.jsonl"]
    assert names(exclude_agents=frozenset({"a1"})) == ["agent-a2.jsonl", "s1.jsonl"]


def test_without_a_session_id_the_newest_workspace_transcript_is_used(tmp_path):
    cwd = Path("/work/my_proj.x")
    assert finance.encode_workspace(cwd) == "-work-my-proj-x"
    base = write_transcripts(tmp_path, "old", [line("2026-10-27T02:30:00Z")], folder="-work-my-proj-x")
    write_transcripts(tmp_path, "new", [line("2026-10-27T02:30:00Z")], folder="-work-my-proj-x")
    os.utime(base / "old.jsonl", (1, 1))
    assert [p.name for p in finance.transcript_files(tmp_path, None, cwd)] == ["new.jsonl"]


def test_price_conversion():
    usage = {"m": finance.ModelUsage(1_000_000, 1_000_000, 1_000_000, 1_000_000)}
    cost, missing = finance.price_usage(usage, {"m": {"input": 1.0, "output": 2.0, "cache_write": 3.0, "cache_read": 4.0}})
    assert cost == pytest.approx(10.0) and missing == []


def test_unpriced_model_makes_cost_unknown():
    assert finance.price_usage({"claude-new-model": finance.ModelUsage(5, 5, 0, 0)}, {}) == (None, ["claude-new-model"])


def test_p80_with_five_matching_tasks():
    s = finance.suggest_budget(ledger_of([(3, c) for c in (0.1, 0.2, 0.3, 0.4, 0.5)]), "claude-code", "research", 3, DEFAULTS)
    assert (s.method, s.n) == ("p80", 5) and s.budget_usd == pytest.approx(0.42)


def test_regression_with_ten_tasks_in_the_playbook():
    pairs = list(zip([1, 1, 2, 2, 2, 4, 4, 5, 5, 5], [0.2, 0.3, 0.5, 0.6, 0.7, 2.0, 2.2, 3.0, 3.1, 3.3]))
    s = finance.suggest_budget(ledger_of(pairs), "claude-code", "research", 3, DEFAULTS)
    assert (s.method, s.n) == ("regression", 10) and s.budget_usd == pytest.approx(1.5153, abs=1e-4)


def test_regression_is_floored_at_the_cheapest_task():
    pairs = list(zip([3, 3, 4, 4, 4, 5, 5, 5, 5, 5], [0.1, 0.1, 2, 2, 2, 5, 5, 5, 5, 5]))
    assert finance.suggest_budget(ledger_of(pairs), "claude-code", "research", 1, DEFAULTS).budget_usd == pytest.approx(0.1)


def test_constant_difficulty_falls_back_to_the_default():
    s = finance.suggest_budget(ledger_of([(2, 0.5)] * 10), "claude-code", "research", 4, DEFAULTS)
    assert s == finance.Suggestion(4.0, "default", 0)


def test_other_platforms_and_unsuccessful_tasks_do_not_count():
    for led in (ledger_of([(3, 0.1)] * 5, platform="codex"), ledger_of([(3, 0.1)] * 5, outcome="failed")):
        assert finance.suggest_budget(led, "claude-code", "research", 3, DEFAULTS).method == "default"


@pytest.mark.usefixtures("isolated_git")
def test_record_measures_claude_code_and_commits_only_the_ledger(tmp_path, monkeypatch, capsys):
    clone, skill = make_clone(tmp_path)
    (skill / "config.toml").write_text(FAKE_PRICES)
    write_transcripts(tmp_path / "claude", "s1", [line("2026-10-27T02:30:00Z")])
    use_claude(monkeypatch, tmp_path / "claude")
    (clone / "notes.txt").write_text("wip\n")
    git(clone, "add", "notes.txt")
    code, out, _ = run_main(capsys, "--skill-dir", str(skill), *RECORD, "--platform", "claude-code")
    text = (skill / "ledger/costs.md").read_text()
    [r] = ledger.parse_ledger(text).tasks
    assert code == 0 and out["sync"]["pushed"] is True
    assert (r["input_tokens"], r["output_tokens"], r["cache_tokens"]) == ("10", "5", "1100")
    assert (r["cost_usd"], r["models"], r["measurement"]) == ("0.0043", "claude-opus-5-5", "measured")
    assert git(clone, "log", "-1", "--format=%s") == "chore(sharron): record task cost [skip ci]"
    assert git(clone, "show", "--name-only", "--format=", "HEAD") == "plugins/workflow/skills/sharron/ledger/costs.md"
    assert git(clone, "diff", "--cached", "--name-only") == "notes.txt"
    assert "secret-text-123" not in text + json.dumps(out)


def test_record_rejects_a_task_recorded_twice(tmp_path):
    skill = make_skill(tmp_path)
    finance.record(skill, row())
    with pytest.raises(ledger.LedgerError, match="already recorded"):
        finance.record(skill, row())
    assert len(ledger.parse_ledger((skill / "ledger/costs.md").read_text()).tasks) == 1


def test_record_without_reported_usage_is_unknown(tmp_path, capsys):
    code, out, _ = run_main(capsys, "--skill-dir", str(make_skill(tmp_path)), *RECORD, "--platform", "work", "--models", "T2,T1")
    assert code == 0 and (out["row"]["cost_usd"], out["row"]["measurement"], out["row"]["models"]) == ("unknown", "unknown", "T2,T1")


def test_unknown_platform_names_are_rejected(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        finance.main(["--skill-dir", str(make_skill(tmp_path)), *RECORD, "--platform", "vscode"])
    assert exc.value.code == 2 and "claude-code" in capsys.readouterr().err


def test_auto_platform_needs_an_explicit_platform(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SHARRON_PLATFORM", raising=False)
    code, _, err = run_main(capsys, "--skill-dir", str(make_skill(tmp_path)), *RECORD)
    assert code == 1 and "--platform" in err


def test_outside_a_clone_the_notice_comes_once(tmp_path, capsys):
    skill = make_skill(tmp_path)
    second_task = [a.replace("-01", "-02") for a in RECORD]
    _, first, _ = run_main(capsys, "--skill-dir", str(skill), *RECORD, "--platform", "work")
    _, second, _ = run_main(capsys, "--skill-dir", str(skill), *second_task, "--platform", "work")
    assert first["sync"]["notice"] and second["sync"]["notice"] is None


@pytest.mark.usefixtures("isolated_git")
def test_failed_commit_leaves_the_row_for_the_next_run(tmp_path):
    clone, skill = make_clone(tmp_path)
    hook = clone / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    first = finance.record(skill, row(task_id="t-20261027-01"))
    assert (first["sync"]["committed"], first["sync"]["reason"]) == (False, "commit-failed")
    hook.unlink()
    assert finance.record(skill, row(task_id="t-20261027-02"))["sync"]["committed"]
    committed = git(clone, "show", "HEAD:plugins/workflow/skills/sharron/ledger/costs.md")
    assert "t-20261027-01" in committed and "t-20261027-02" in committed


def test_correct_marks_a_task_and_excludes_it(tmp_path, capsys):
    skill = make_skill(tmp_path)
    for i in range(1, 6):
        finance.record(skill, row(task_id=f"t-20261027-{i:02d}", cost_usd="0.1000"))
    finance.correct(skill, "t-20261027-01", date(2026, 10, 28))
    led = ledger.parse_ledger((skill / "ledger/costs.md").read_text())
    assert led.corrections == [{"task_id": "t-20261027-01", "date": "2026-10-28"}]
    assert finance.suggest_budget(led, "claude-code", "research", 3, DEFAULTS).method == "default"
    code, _, err = run_main(capsys, "--skill-dir", str(skill), "correct", "--task-id", "t-20261027-09")
    assert code == 1 and "t-20261027-09" in err


def test_usage_flags_an_overrun(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    (skill / "config.toml").write_text(FAKE_PRICES)
    write_transcripts(tmp_path / "claude", "s1", [line("2026-10-27T02:30:00Z", i=1_600_000, o=0, cw=0, cr=0)])
    use_claude(monkeypatch, tmp_path / "claude")
    code, out, _ = run_main(capsys, "--skill-dir", str(skill), "usage", "--platform", "claude-code",
                            "--since", "2026-10-27T10:00:00+08:00", "--budget", "1.0")
    assert code == 0 and out["cost_usd"] == pytest.approx(1.6) and out["over_budget"] is True
    assert out["limit_usd"] == pytest.approx(1.5)


def test_suggest_cli_prints_its_basis(tmp_path, capsys):
    code, out, _ = run_main(capsys, "--skill-dir", str(make_skill(tmp_path)), "suggest", "--platform", "claude-code",
                            "--playbook", "research", "--difficulty", "3")
    assert code == 0 and out == {"budget_usd": 1.5, "method": "default", "n": 0}


def test_record_with_no_usage_since_the_start_time_is_unknown(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    (skill / "config.toml").write_text(FAKE_PRICES)
    write_transcripts(tmp_path / "claude", "s1", [line("2026-10-27T01:59:00Z")])  # before --since
    use_claude(monkeypatch, tmp_path / "claude")
    code, out, _ = run_main(capsys, "--skill-dir", str(skill), *RECORD, "--platform", "claude-code", "--models", "T2")
    assert code == 0 and "no usage" in out["note"]
    assert (out["row"]["measurement"], out["row"]["cost_usd"], out["row"]["input_tokens"]) == ("unknown", "unknown", "unknown")
    assert ledger.successful_rows(ledger.parse_ledger((skill / "ledger/costs.md").read_text())) == []


def test_record_with_no_usage_uses_the_reported_flags(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    write_transcripts(tmp_path / "claude", "s1", [line("2026-10-27T01:59:00Z")])
    use_claude(monkeypatch, tmp_path / "claude")
    code, out, _ = run_main(capsys, "--skill-dir", str(skill), *RECORD, "--platform", "claude-code",
                            "--input-tokens", "7", "--output-tokens", "3", "--cache-tokens", "0", "--cost-usd", "0.5")
    assert code == 0 and (out["row"]["measurement"], out["row"]["cost_usd"], out["row"]["input_tokens"]) == ("measured", "0.5000", "7")


def test_usage_with_no_usage_since_the_start_time_is_unknown(tmp_path, monkeypatch, capsys):
    skill = make_skill(tmp_path)
    write_transcripts(tmp_path / "claude", "s1", [line("2026-10-27T01:59:00Z")])
    use_claude(monkeypatch, tmp_path / "claude")
    code, out, _ = run_main(capsys, "--skill-dir", str(skill), "usage", "--platform", "claude-code",
                            "--since", "2026-10-27T10:00:00+08:00", "--budget", "1.0")
    assert code == 0 and "no usage" in out["note"]
    assert (out["measurement"], out["cost_usd"], out["limit_usd"], out["over_budget"]) == ("unknown", None, None, None)
