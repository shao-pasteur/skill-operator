import json

import pytest

from sharron_support import load, make_skill

detect_stack = load("detect_stack")
SHA = "0123456789abcdef0123456789abcdef01234567"


def workspace(tmp_path, files):
    root = tmp_path / "ws"
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def entry(name, tags=(), roles=("engineer",), domains=("coding",), min_tier="T2", status="active", ref=SHA):
    return (f'[[skills]]\nname = "{name}"\nrepo = "owner/repo"\nstatus = "{status}"\nroles = {json.dumps(list(roles))}\n'
            f'playbooks = ["*"]\ndomains = {json.dumps(list(domains))}\ntags = {json.dumps(list(tags))}\n'
            f'min_tier = "{min_tier}"\nref = "{ref}"\n')


def registry(tmp_path, *entries):
    path = tmp_path / "registry.toml"
    path.write_text("schema_version = 1\n\n" + "\n".join(entries))
    return detect_stack.load_registry(path)


def select(reg, tags, limit=4, **kw):
    args = {"role": "engineer", "playbook": "coding", "domain": "coding", "tier": "T2", **kw}
    chosen, dropped = detect_stack.select_skills(reg, tags=set(tags), limit=limit, **args)
    return [e.name for e in chosen], [e.name for e in dropped]


@pytest.mark.parametrize("files,expected", [
    ({"pyproject.toml": "[project]\n", "app/main.py": ""}, {"python"}),
    ({"package.json": '{"dependencies": {"react": "18.3.1"}}', "tsconfig.json": "{}"}, {"javascript", "typescript", "frontend"}),
    ({"Chart.yaml": "apiVersion: v2\n", "templates/deploy.yaml": "apiVersion: apps/v1\nkind: Deployment\n"}, {"helm", "kubernetes"}),
    ({"modules/net/main.tf": 'resource "a" "b" {}\n'}, {"terraform"}),
    ({"bin/backup": "#!/usr/bin/env bash\necho hi\n", "lib/util.sh": "echo\n"}, {"bash"}),
    ({"pyproject.toml": "", "Dockerfile": "FROM python:3.12\n",
      "web/package.json": '{"dependencies": {"vue": "3.5.0", "three": "0.170.0"}}'},
     {"python", "docker", "javascript", "frontend", "threejs"}),
    ({"go.mod": "module x\n", "Cargo.toml": "", "wrangler.toml": ""}, {"go", "rust", "cloudflare"}),
])
def test_detect_tags(tmp_path, files, expected):
    assert detect_stack.detect_tags(workspace(tmp_path, files)) == expected


def test_ignored_folders_and_depth_limit(tmp_path):
    root = workspace(tmp_path, {"node_modules/react/package.json": "{}", ".venv/pyproject.toml": "", "a/b/c/d/go.mod": ""})
    assert detect_stack.detect_tags(root) == set()


def test_frontend_skill_never_selected_for_a_backend_workspace(tmp_path):
    reg = registry(tmp_path, entry("taste-skill", tags=("frontend", "ui-design")), entry("modern-python", tags=("python",)), entry("tdd"))
    tags = detect_stack.detect_tags(workspace(tmp_path, {"pyproject.toml": ""})) | {"backend"}
    assert select(reg, tags) == (["modern-python", "tdd"], [])


def test_most_specific_then_lower_tier_win(tmp_path):
    reg = registry(tmp_path, entry("tdd"), entry("modern-python", tags=("python",)),
                   entry("python-testing-patterns", tags=("python", "testing")),
                   entry("python-error-handling", tags=("python",), min_tier="T1"))
    assert select(reg, {"python", "testing"}, limit=2) == (
        ["python-testing-patterns", "python-error-handling"], ["modern-python", "tdd"])


def test_role_domain_tier_and_status_filters(tmp_path):
    reg = registry(tmp_path, entry("teach", roles=("tutor",), domains=("learning",)), entry("big", min_tier="T3"),
                   entry("off", status="disabled"), entry("any", roles=("*",), domains=("*",)))
    assert select(reg, set()) == (["any"], [])


@pytest.mark.parametrize("kwargs,word", [
    ({"tags": ("frontend-x",)}, "frontend-x"), ({"roles": ("wizard",)}, "wizard"),
    ({"min_tier": "T0"}, "min_tier"), ({"ref": "main"}, "ref"),
])
def test_invalid_entries_are_rejected(tmp_path, kwargs, word):
    with pytest.raises(detect_stack.RegistryError, match=word):
        registry(tmp_path, entry("x", **kwargs))


def test_select_cli_reports_matched_tags(tmp_path, capsys):
    skill = make_skill(tmp_path / "s")
    (skill / "registry.toml").write_text("schema_version = 1\n\n" + entry("python-testing-patterns", tags=("python", "testing"))
                                         + "\n" + entry("taste-skill", tags=("frontend", "ui-design")))
    ws = workspace(tmp_path, {"pyproject.toml": ""})
    assert detect_stack.main(["--skill-dir", str(skill), "select", "--role", "engineer", "--playbook", "coding",
                              "--domain", "coding", "--tier", "T2", "--workspace", str(ws), "--tags", "testing,backend"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tags"] == ["backend", "python", "testing"]
    assert [(s["name"], s["matched"]) for s in out["skills"]] == [("python-testing-patterns", ["python", "testing"])]


def test_shipped_registry_lists_this_repos_two_skills():
    reg = detect_stack.load_registry(detect_stack.config.DEFAULT_SKILL_DIR / "registry.toml")
    own = {e.name: e for e in reg.skills if e.ref == "self"}
    assert {name: e.roles for name, e in own.items()}.items() >= {
        "research-method": ("researcher",), "verify-evidence": ("verifier",)}.items()
    assert set(own["research-method"].install) == {"claude-code", "codex", "copilot"}


def test_tools_and_install_tables_are_loaded_and_checked(tmp_path):
    ok = ('[[tools]]\nname = "scan"\ncheck = "scan --version"\ninstall = ""\nrun = "scan ."\nsends_data = true\n')
    reg = registry(tmp_path, entry("x") + '\n[skills.install]\nclaude-code = "do it"\n', ok)
    assert reg.skills[0].install == {"claude-code": "do it"}
    assert reg.tools == (detect_stack.Tool("scan", "scan --version", "", "scan .", True),)
    with pytest.raises(detect_stack.RegistryError, match="auto"):
        registry(tmp_path, entry("x") + '\n[skills.install]\nauto = "do it"\n')
    with pytest.raises(detect_stack.RegistryError, match="sends_data"):
        registry(tmp_path, entry("x"), ok.replace("true", '"yes"'))


def test_ref_self_is_accepted_and_schema_version_is_checked(tmp_path):
    assert registry(tmp_path, entry("x", ref="self")).skills[0].ref == "self"
    (tmp_path / "registry.toml").write_text("schema_version = 2\n")
    with pytest.raises(detect_stack.RegistryError, match="schema_version"):
        detect_stack.load_registry(tmp_path / "registry.toml")


def test_cli_rejects_unknown_tags_and_tags_command_lists_detected(tmp_path, capsys):
    skill = make_skill(tmp_path / "s")
    ws = workspace(tmp_path, {"go.mod": ""})
    base = ["--skill-dir", str(skill), "select", "--role", "engineer", "--playbook", "coding", "--domain", "coding",
            "--tier", "T2", "--workspace", str(ws)]
    assert detect_stack.main([*base, "--tags", "nonsense"]) == 1
    assert "nonsense" in capsys.readouterr().err
    assert detect_stack.main(["tags", "--workspace", str(ws)]) == 0
    assert json.loads(capsys.readouterr().out) == {"tags": ["go"]}
