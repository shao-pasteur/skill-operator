import subprocess

import pytest

from skillops.catalog import load_catalog
from skillops.release_notes import changed_skill_names, git_changed_paths, render_release_notes


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def init_repo(path):
    git(path.parent, "init", "-q", str(path))
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "t")


def test_changed_skill_names(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("finance", "bar")
    cat = load_catalog(repo.root)
    paths = [
        "plugins/dev/skills/foo/SKILL.md",
        "plugins/dev/skills/foo/references/a.md",
        "plugins/dev/.claude-plugin/plugin.json",
        "README.md",
        "plugins/finance/skills/gone/SKILL.md",
    ]
    assert changed_skill_names(cat, paths) == ["foo"]


@pytest.mark.parametrize("base", [None, "", "0" * 40, "deadbeef" * 5])
def test_git_changed_paths_unknown_base_returns_none(tmp_path, base):
    repo_dir = tmp_path / "g"
    init_repo(repo_dir)
    (repo_dir / "a.txt").write_text("a")
    git(repo_dir, "add", ".")
    git(repo_dir, "commit", "-qm", "a")
    assert git_changed_paths(repo_dir, base, "HEAD") is None


def test_git_changed_paths_real_diff(tmp_path):
    repo_dir = tmp_path / "g"
    init_repo(repo_dir)
    (repo_dir / "a.txt").write_text("a")
    (repo_dir / "b.txt").write_text("b")
    git(repo_dir, "add", ".")
    git(repo_dir, "commit", "-qm", "one")
    base = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo_dir / "b.txt").write_text("bb")
    git(repo_dir, "commit", "-qam", "two")
    assert git_changed_paths(repo_dir, base, "HEAD") == ["b.txt"]


def test_notes_lists_changed_web_skills(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("dev", "baz")
    repo.add_skill("dev", "bar", frontmatter={"name": "bar", "description": "x", "metadata": {"web": "false"}})
    notes = render_release_notes(load_catalog(repo.root), ["foo", "bar"])
    assert "## 需要重新上傳" in notes
    assert "- [`foo`](https://github.com/tester/test-market/releases/download/latest/foo.zip)" in notes
    head, tail = notes.split("## 所有網頁版 skill")
    assert "`bar`" not in head and "`baz`" not in head
    assert "`baz`" in tail and "`foo`" in tail and "`bar`" not in tail


def test_notes_all_changed_when_none(repo):
    repo.add_skill("dev", "foo")
    repo.add_skill("dev", "baz")
    head = render_release_notes(load_catalog(repo.root), None).split("## 所有網頁版 skill")[0]
    assert "`foo`" in head and "`baz`" in head


def test_notes_nothing_changed(repo):
    repo.add_skill("dev", "foo")
    notes = render_release_notes(load_catalog(repo.root), [])
    assert "_這次沒有網頁版 skill 變動。_" in notes


def test_notes_no_web_skills(repo):
    notes = render_release_notes(load_catalog(repo.root), None)
    assert "_目前沒有網頁版 skill。_" in notes


@pytest.mark.parametrize("base,head", [("--output={out}", "HEAD"), ("HEAD", "-p")])
def test_git_changed_paths_rejects_option_like_revs(tmp_path, base, head):
    base = base.format(out=tmp_path / "x")
    repo_dir = tmp_path / "g"
    init_repo(repo_dir)
    (repo_dir / "a.txt").write_text("a")
    git(repo_dir, "add", ".")
    git(repo_dir, "commit", "-qm", "a")
    assert git_changed_paths(repo_dir, base, head) is None
    assert not (tmp_path / "x").exists()
