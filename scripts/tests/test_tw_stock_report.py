import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "plugins/finance/skills/tw-stock-daily-tracker/scripts/build_report.py"
)
PAYLOAD = {"date": "2026-10-26", "phase": "premarket", "time_label": "0850", "stocks": []}


@pytest.fixture
def report():
    spec = importlib.util.spec_from_file_location("build_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_accepts_valid_payload(report, tmp_path):
    path, _ = report.build(dict(PAYLOAD), tmp_path / "Daily")
    assert path == tmp_path / "Daily/2026-10-26/reports/0850_premarket.md"


@pytest.mark.parametrize("field,value", [
    ("date", "../../x"),
    ("time_label", "../x"),
    ("phase", "../x"),
    ("stocks", [{"symbol": "../../x"}]),
])
def test_build_rejects_unsafe_payload_parts(report, tmp_path, field, value):
    payload = {**PAYLOAD, field: value}
    with pytest.raises(ValueError):
        report.build(payload, tmp_path / "base" / "Daily")
    assert not (tmp_path / "x").exists() and not (tmp_path / "base" / "x").exists()


def test_mac_notify_passes_text_as_arguments(report, monkeypatch):
    calls = []
    monkeypatch.setattr(report.sys, "platform", "darwin")
    monkeypatch.setattr(report.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    message = 'a" & (do shell script "touch /tmp/pwned") & "'
    report.mac_notify("Title", message)
    [cmd] = calls
    scripts = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-e"]
    assert all(message not in s for s in scripts)
    assert message in cmd and "Title" in cmd


def test_tilde_in_env_is_expanded(report, tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TW_STOCK_INVESTING_DIR", "~/vault")
    monkeypatch.setattr(sys, "argv", ["build_report.py", "--input", str(payload), "--capital", "1"])
    report.main()
    assert (tmp_path / "vault/Daily/2026-10-26/reports/0850_premarket.md").exists()
    assert not (cwd / "~").exists()
