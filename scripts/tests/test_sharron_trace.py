import io
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from sharron_support import load
from skillops.validate import _PERSONAL_PATH_RES

trace = load("trace")
NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
HOME = "/Users/alice"
GH_TOKEN = "gh" + "p_" + "a" * 36  # concatenated so gitleaks does not flag this file
KEY_BLOCK = "-----BEGIN " + "PRIVATE KEY-----\nMIIEsecretbody\n-----END " + "PRIVATE KEY-----"


def test_append_writes_one_line_per_call(tmp_path):
    first = trace.append(tmp_path, "t-20261027-01", "brief", {"goal": "x"}, now=NOW, home=HOME)
    second = trace.append(tmp_path, "t-20261027-01", "report", {"status": "done"}, now=NOW, home=HOME)
    lines = [json.loads(line) for line in first.read_text().splitlines()]
    assert first == second == tmp_path / "state/traces/t-20261027-01.jsonl"
    assert [(l["kind"], l["payload"]) for l in lines] == [("brief", {"goal": "x"}), ("report", {"status": "done"})]


@pytest.mark.parametrize("payload,secret", [
    ({"api_key": "abc123xyz"}, "abc123xyz"),
    ({"context": "Authorization: Bearer abcdefghijklmnop"}, "abcdefghijklmnop"),
    ({"context": f"push with {GH_TOKEN}"}, GH_TOKEN),
    ({"context": "password=hunter2hunter2"}, "hunter2hunter2"),
    ({"files": [KEY_BLOCK]}, "MIIEsecretbody"),
])
def test_secrets_are_redacted(tmp_path, payload, secret):
    text = trace.append(tmp_path, "t-20261027-01", "brief", payload, now=NOW, home=HOME).read_text()
    assert secret not in text and "[REDACTED" in text


def test_trace_files_pass_the_repo_personal_path_check(tmp_path):
    payload = {"files": [f"{HOME}/proj/a.py", "/Users/bob/x", "/home/carol/y", r"C:\Users\dave\z"]}
    text = trace.append(tmp_path, "t-20261027-01", "brief", payload, now=NOW, home=HOME).read_text()
    assert "~/proj/a.py" in text
    assert [m.group(0) for p in _PERSONAL_PATH_RES for m in p.finditer(text)] == []


def make_traces(tmp_path, ages_in_hours):
    folder = tmp_path / "state/traces"
    folder.mkdir(parents=True)
    for i, hours in enumerate(ages_in_hours, 1):
        path = folder / f"t-20261027-{i:02d}.jsonl"
        path.write_text("{}\n")
        stamp = (NOW - timedelta(hours=hours)).timestamp()
        os.utime(path, (stamp, stamp))


def test_prune_keeps_the_newest_fifty(tmp_path):
    make_traces(tmp_path, range(1, 53))
    assert trace.prune(tmp_path, now=NOW) == ["t-20261027-51", "t-20261027-52"]


def test_prune_drops_traces_older_than_thirty_days(tmp_path):
    make_traces(tmp_path, [29 * 24, 31 * 24])
    assert trace.prune(tmp_path, now=NOW) == ["t-20261027-02"]


def test_append_prunes_when_a_new_task_starts(tmp_path):
    make_traces(tmp_path, range(1, 51))
    trace.append(tmp_path, "t-20261028-01", "brief", {}, now=NOW, home=HOME)
    assert len(list((tmp_path / "state/traces").glob("*.jsonl"))) == 50
    assert not (tmp_path / "state/traces/t-20261027-50.jsonl").exists()


@pytest.mark.parametrize("task_id", ["../x", "t-20261027-01/../../y", ""])
def test_unsafe_task_ids_are_rejected(tmp_path, task_id):
    with pytest.raises(ValueError):
        trace.append(tmp_path, task_id, "brief", {}, now=NOW, home=HOME)
    assert not (tmp_path / "x").exists() and not (tmp_path.parent / "y").exists()


def test_a_trailing_newline_is_not_a_valid_task_id(tmp_path):
    with pytest.raises(ValueError):
        trace.append(tmp_path, "t-20261027-01\n", "brief", {}, now=NOW, home=HOME)


def test_unknown_kinds_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        trace.append(tmp_path, "t-20261027-01", "chat", {}, now=NOW, home=HOME)


def test_ordinary_words_and_ids_survive_redaction():
    text = "task-abcdefghijklmnopqrst in /Users/alice-bob/x and ~/y"
    assert trace.redact(text, "/Users/alice") == "task-abcdefghijklmnopqrst in /Users/<user>/x and ~/y"


def test_cli_appends_and_prunes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"goal": "x"}'))
    assert trace.main(["--skill-dir", str(tmp_path), "append", "--task-id", "t-20261027-01", "--kind", "brief"]) == 0
    assert json.loads(capsys.readouterr().out) == {"path": str(tmp_path / "state/traces/t-20261027-01.jsonl")}
    assert trace.main(["--skill-dir", str(tmp_path), "prune"]) == 0
    assert json.loads(capsys.readouterr().out) == {"removed": []}


def test_cli_rejects_bad_input_with_one_stderr_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("[]"))
    assert trace.main(["--skill-dir", str(tmp_path), "append", "--task-id", "t-20261027-01", "--kind", "brief"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and len(captured.err.splitlines()) == 1
