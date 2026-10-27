import importlib
import subprocess

import pytest

from sharron_support import SKILL_SRC, load, make_skill

config = load("config")
RUN = SKILL_SRC / "scripts/run.sh"


def skill_with(tmp_path, text=None):
    skill = make_skill(tmp_path)
    if text is not None:
        (skill / "config.toml").write_text(text, encoding="utf-8")
    return skill


def test_defaults_apply_without_config_toml(tmp_path):
    s = config.load_settings(skill_with(tmp_path), environ={})
    assert s.values["max_parallel_subagents"] == 3 and s.values["max_skills_per_brief"] == 4
    assert s.values["budget"]["default_per_task"]["3"] == 1.5 and s.values["risk"]["large_amount"] == 3000
    assert s.sources["roles.reviewer"] == "default"


def test_config_toml_overrides_one_key(tmp_path):
    s = config.load_settings(skill_with(tmp_path, '[roles]\nreviewer = "T3"\n'), environ={})
    assert (s.values["roles"]["reviewer"], s.values["roles"]["planner"]) == ("T3", "T2")
    assert (s.sources["roles.reviewer"], s.sources["roles.planner"]) == ("config.toml", "default")


def test_environment_platform_wins(tmp_path):
    s = config.load_settings(skill_with(tmp_path, 'platform = "codex"\n'), environ={"SHARRON_PLATFORM": "work"})
    assert (s.values["platform"], s.sources["platform"]) == ("work", "SHARRON_PLATFORM")


def test_unknown_key_is_a_warning(tmp_path):
    problems = config.validate_settings(skill_with(tmp_path, "colour = 1\n"), environ={})
    assert [(p.level, p.key) for p in problems] == [("warning", "colour")]


@pytest.mark.parametrize("text,key,allowed", [
    ('[roles]\nreviewer = "T4"\n', "roles.reviewer", "T1, T2, T3"),
    ('platform = "vscode"\n', "platform", "auto, claude-code, codex, copilot, cursor, work, hybrid"),
    ("[risk]\nsmall_amount = -5\n", "risk.small_amount", "≥ 0"),
    ("[risk]\nlarge_amount = 100\n", "risk.large_amount", "risk.small_amount"),
])
def test_invalid_values_name_the_allowed_ones(tmp_path, text, key, allowed):
    [p] = config.validate_settings(skill_with(tmp_path, text), environ={})
    assert (p.level, p.key) == ("error", key) and allowed in p.message


def test_invalid_environment_platform_is_an_error(tmp_path):
    [p] = config.validate_settings(skill_with(tmp_path), environ={"SHARRON_PLATFORM": "vscode"})
    assert p.key == "platform" and "claude-code" in p.message


def test_shipped_example_is_clean(tmp_path):
    assert config.validate_settings(skill_with(tmp_path), environ={}) == []


def test_show_and_validate_cli(tmp_path, capsys):
    skill = skill_with(tmp_path, '[roles]\nreviewer = "T3"\n')
    assert config.main(["--skill-dir", str(skill), "show"]) == 0
    assert 'roles.reviewer = "T3"  # config.toml' in capsys.readouterr().out.splitlines()
    (skill / "config.toml").write_text("[roles\n", encoding="utf-8")
    assert config.main(["--skill-dir", str(skill), "validate"]) == 1
    assert "config.toml" in capsys.readouterr().out


def fake_python(bin_dir, name, new_enough):
    path = bin_dir / name
    path.write_text(f'#!/bin/sh\n[ "$1" = "-c" ] && exit {0 if new_enough else 1}\necho "{name} $*"\n')
    path.chmod(0o755)


def run_sh(bin_dir, *args):
    return subprocess.run(["/bin/sh", str(RUN), *args], env={"PATH": str(bin_dir)}, capture_output=True, text=True)


def test_run_sh_skips_old_python3(tmp_path):
    fake_python(tmp_path, "python3", new_enough=False)
    fake_python(tmp_path, "python3.11", new_enough=True)
    result = run_sh(tmp_path, "config.py", "show")
    assert result.returncode == 0 and result.stdout.strip() == f"python3.11 {RUN.parent}/config.py show"


def test_run_sh_reports_missing_python(tmp_path):
    fake_python(tmp_path, "python3", new_enough=False)
    result = run_sh(tmp_path, "config.py")
    assert result.returncode == 1 and "Python 3.11" in result.stderr


def test_run_sh_rejects_unknown_scripts(tmp_path):
    assert run_sh(tmp_path, "../evil.py").returncode == 2


# The tests above are the plan's. The ones below cover rows of the settings table and behaviours
# of config.py that those do not reach.


@pytest.fixture(autouse=True)
def without_sharron_platform(monkeypatch):
    """For every test in this file: main() reads os.environ, so keep a real SHARRON_PLATFORM out of it."""
    monkeypatch.delenv("SHARRON_PLATFORM", raising=False)


@pytest.mark.parametrize("text,expected", [
    ('auto_install = "yes"\n', [("error", "auto_install")]),
    ("max_parallel_subagents = true\n", [("error", "max_parallel_subagents")]),
    ("max_skills_per_brief = 11\n", [("error", "max_skills_per_brief")]),
    ("max_skills_per_brief = 10\nmax_parallel_subagents = 1\n", []),
    ("[platforms.vscode]\nx = 1\n", [("warning", "platforms.vscode")]),
    ("[platforms.auto]\nx = 1\n", [("warning", "platforms.auto")]),
    ("[platforms.codex.models]\nT1 = 5\n", [("error", "platforms.codex.models.T1")]),
    ('[platforms.hybrid]\navailable = ["a", 1]\n', [("error", "platforms.hybrid.available")]),
    ('[platforms.hybrid]\navailable = ["a", "b"]\n', []),
    ("[platforms.work]\navailable = []\n", [("warning", "platforms.work.available")]),
    ('[roles]\nintern = "T1"\n', [("warning", "roles.intern")]),
    ('[prices."gpt-5.1"]\ninput = -1\noutput = 1\ncache_write = 0\ncache_read = 0\n', [("error", 'prices."gpt-5.1".input')]),
    ("[prices.m]\ninput = 1\noutput = 2\n", [("error", "prices.m.cache_write"), ("error", "prices.m.cache_read")]),
    ('[risk]\ncurrency = "twd"\n', [("error", "risk.currency")]),
    ("[risk]\nsmall_amount = 3000\n", [("error", "risk.large_amount")]),
    ('[budget.default_per_task]\n"3" = 0\n', [("error", "budget.default_per_task.3")]),
    ("[budget]\noverrun_factor = 1\n", [("error", "budget.overrun_factor")]),
    ("[standing_orders]\nalways = [1]\n", [("error", "standing_orders.always")]),
    ('[installed.demo]\nsource = "x"\nversion = "1"\ndate = "2026-10-28"\nplatform = "claude-code"\n', []),
    ("[installed.demo]\ndate = 2026-10-28\n", [("error", "installed.demo.date")]),
    ('roles = "T3"\n', [("error", "roles")]),
])
def test_rules_of_the_settings_table(tmp_path, text, expected):
    problems = config.validate_settings(skill_with(tmp_path, text), environ={})
    assert [(p.level, p.key) for p in problems] == expected


def test_toml_syntax_error_raises_config_error_naming_config_toml(tmp_path):
    with pytest.raises(config.ConfigError, match=r"^config\.toml: .+"):
        config.load_settings(skill_with(tmp_path, "[roles\n"), environ={})


def test_empty_environment_platform_counts_as_unset(tmp_path):
    skill = skill_with(tmp_path)
    s = config.load_settings(skill, environ={"SHARRON_PLATFORM": ""})
    assert (s.values["platform"], s.sources["platform"]) == ("auto", "default")
    assert config.validate_settings(skill, environ={"SHARRON_PLATFORM": ""}) == []


def test_tables_merge_while_lists_and_scalars_replace(tmp_path):
    skill = skill_with(tmp_path, "xs = [3]\n[t]\nb = 5\n")
    (skill / "config.example.toml").write_text("xs = [1, 2]\n[t]\na = 1\nb = 2\n", encoding="utf-8")
    s = config.load_settings(skill, environ={})
    assert s.values == {"xs": [3], "t": {"a": 1, "b": 5}}
    assert s.sources == {"xs": "config.toml", "t.a": "default", "t.b": "config.toml"}


def test_a_scalar_replaces_a_whole_default_table(tmp_path):
    skill = skill_with(tmp_path, "t = 5\n")
    (skill / "config.example.toml").write_text("[t]\na = 1\nb = 2\n", encoding="utf-8")
    s = config.load_settings(skill, environ={})
    assert (s.values, s.sources) == ({"t": 5}, {"t": "config.toml"})


def test_show_lists_the_examples_keys_first_then_those_only_config_toml_has(tmp_path, capsys):
    example_keys = list(config.load_settings(skill_with(tmp_path / "plain"), environ={}).sources)
    mine = skill_with(tmp_path / "mine", '[roles]\nintern = "T1"\nreviewer = "T3"\n[prices."gpt-5.1"]\ninput = 1\n')
    assert config.main(["--skill-dir", str(mine), "show"]) == 0
    shown = [line.split(" = ")[0] for line in capsys.readouterr().out.splitlines()]
    assert shown == example_keys + ["roles.intern", 'prices."gpt-5.1".input']


def test_show_prints_non_ascii_text_as_it_is(tmp_path, capsys):
    skill = skill_with(tmp_path, '[standing_orders]\nalways = ["回覆一律用繁體中文"]\n')
    assert config.main(["--skill-dir", str(skill), "show"]) == 0
    assert 'standing_orders.always = ["回覆一律用繁體中文"]  # config.toml' in capsys.readouterr().out.splitlines()


def test_shared_vocabularies():
    assert config.TIERS == ("T1", "T2", "T3")
    assert config.ROLES == (
        "sharron", "planner", "researcher", "verifier", "reviewer", "security", "analyst",
        "writer", "engineer", "diagnostician", "operator", "tutor", "finance",
    )
    assert config.PLAYBOOKS == (
        "simple-answer", "research", "planning", "action", "decision-support",
        "learning", "coding", "settings-help", "custom", "maintenance",
    )


@pytest.mark.parametrize("task_id,valid", [
    ("t-20261027-01", True),
    ("m-20261027-12", True),
    ("t-20261027-100", True),
    ("T-20261027-01", False),
    ("t-2026102-01", False),
    ("t-20261027-1", False),
    ("t-20261027-01\n", False),
    ("t-" + "\N{ARABIC-INDIC DIGIT TWO}" * 8 + "-01", False),  # Unicode digits are not ASCII digits
])
def test_task_id_pattern(task_id, valid):
    assert bool(config.TASK_ID_RE.fullmatch(task_id)) is valid


def test_validate_prints_each_problem_then_a_summary(tmp_path, capsys):
    skill = skill_with(tmp_path, 'colour = 1\n[roles]\nreviewer = "T4"\n')
    assert config.main(["--skill-dir", str(skill), "validate"]) == 1
    *problem_lines, summary = capsys.readouterr().out.splitlines()
    assert sorted(problem_lines) == [
        'ERROR roles.reviewer: "T4" is not allowed; use one of: T1, T2, T3',
        "WARN colour: unknown setting; it has no effect",
    ]
    assert summary == "1 error(s), 1 warning(s)"


def test_validate_exits_zero_when_there_are_only_warnings(tmp_path, capsys):
    skill = skill_with(tmp_path, "colour = 1\n")
    assert config.main(["--skill-dir", str(skill), "validate"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "WARN colour: unknown setting; it has no effect",
        "0 error(s), 1 warning(s)",
    ]


def test_invalid_platform_is_reported_for_config_toml_and_for_the_environment(tmp_path):
    skill = skill_with(tmp_path, 'platform = "vscode"\n')
    problems = config.validate_settings(skill, environ={"SHARRON_PLATFORM": "nope"})
    assert [(p.key, "(from SHARRON_PLATFORM)" in p.message) for p in problems] == [("platform", False), ("platform", True)]


def test_an_unquoted_toml_date_is_shown_as_written(tmp_path):
    [p] = config.validate_settings(skill_with(tmp_path, "[installed.demo]\ndate = 2026-10-28\n"), environ={})
    assert p.message == "2026-10-28 is not allowed; use a string in quotes"


def test_load_returns_the_module_that_sibling_scripts_import():
    module = load("config")
    assert module is importlib.import_module("config")
    assert (SKILL_SRC / "scripts/config.py").samefile(module.__file__)
