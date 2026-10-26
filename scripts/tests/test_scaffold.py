import pytest

from cli import main
from skillops.catalog import load_catalog
from skillops.scaffold import ScaffoldError, import_skill, new_skill
from skillops.validate import validate_catalog

LONG_DESC = "說明" * 30


def make_src(tmp_path, name="foo", extra=""):
    src = tmp_path / "ext" / name
    (src / "scripts" / "__pycache__").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {LONG_DESC}\nmetadata:\n  web: \"false\"\n---\n{extra}",
        encoding="utf-8",
    )
    (src / "scripts" / "a.py").write_text("x = 1\n")
    (src / "scripts" / "__pycache__" / "a.pyc").write_text("")
    (src / ".DS_Store").write_text("")
    return src


def test_new_skill_creates_template(repo):
    p = new_skill(repo.root, "dev", "my-skill")
    assert p == repo.root / "plugins/dev/skills/my-skill"
    text = (p / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: my-skill\n")
    issues = validate_catalog(load_catalog(repo.root))
    assert any("樣板" in i.message for i in issues if i.level == "error")


@pytest.mark.parametrize("name", ["Bad", "a--b", "x" * 65])
def test_new_skill_rejects_bad_name(repo, name):
    with pytest.raises(ScaffoldError, match="name"):
        new_skill(repo.root, "dev", name)


def test_new_skill_unknown_category(repo):
    with pytest.raises(ScaffoldError, match="ghost"):
        new_skill(repo.root, "ghost", "foo")


def test_new_skill_duplicate_name(repo):
    repo.add_skill("finance", "foo")
    with pytest.raises(ScaffoldError, match="已存在"):
        new_skill(repo.root, "dev", "foo")


def test_import_copies_and_filters(repo, tmp_path):
    dest = import_skill(repo.root, make_src(tmp_path), "dev")
    assert dest == repo.root / "plugins/dev/skills/foo"
    files = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert files == ["SKILL.md", "scripts/a.py"]


def test_import_requires_skill_md(repo, tmp_path):
    src = tmp_path / "ext" / "foo"
    src.mkdir(parents=True)
    with pytest.raises(ScaffoldError, match="SKILL.md"):
        import_skill(repo.root, src, "dev")


def test_import_refuses_existing(repo, tmp_path):
    repo.add_skill("dev", "foo")
    with pytest.raises(ScaffoldError, match="已存在"):
        import_skill(repo.root, make_src(tmp_path), "dev")


def test_cli_import_reports_issues(repo, tmp_path, capsys):
    src = make_src(tmp_path, extra="放在 /Users/alice/x\n")
    assert main(["--root", str(repo.root), "import", "--src", str(src), "--category", "dev"]) == 1
    assert "個人路徑" in capsys.readouterr().out
    assert (repo.root / "plugins/dev/skills/foo/SKILL.md").exists()


def test_cli_new_prints_path(repo, capsys):
    assert main(["--root", str(repo.root), "new", "--category", "dev", "--name", "bar"]) == 0
    assert "plugins/dev/skills/bar" in capsys.readouterr().out


def test_cli_new_error(repo, capsys):
    assert main(["--root", str(repo.root), "new", "--category", "ghost", "--name", "bar"]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_import_rejects_symlinks(repo, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    src = make_src(tmp_path)
    (src / "references").mkdir()
    (src / "references" / "leak.md").symlink_to(secret)
    with pytest.raises(ScaffoldError, match="symlink"):
        import_skill(repo.root, src, "dev")
    assert not (repo.root / "plugins/dev/skills/foo").exists()


def test_import_skips_env_files(repo, tmp_path):
    src = make_src(tmp_path)
    (src / ".env").write_text("OPENAI_API_KEY=sk-test")
    (src / ".env.local").write_text("X=1")
    dest = import_skill(repo.root, src, "dev")
    assert not (dest / ".env").exists() and not (dest / ".env.local").exists()
