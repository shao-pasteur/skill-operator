import subprocess

from cli import main


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def init(repo):
    git(repo.root, "init", "-q")
    git(repo.root, "config", "user.email", "t@example.com")
    git(repo.root, "config", "user.name", "t")
    main(["--root", str(repo.root), "build"])
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-qm", "init")


def test_first_skill_in_new_category_needs_new_manifests_staged(repo, capsys):
    init(repo)
    repo.add_skill("dev", "foo")
    git(repo.root, "add", "plugins/dev/skills")
    assert main(["--root", str(repo.root), "precommit"]) == 1
    git(repo.root, "add", "-u")
    capsys.readouterr()
    assert main(["--root", str(repo.root), "precommit"]) == 1
    out = capsys.readouterr().out
    assert "git add" in out and "plugins/dev/.claude-plugin/plugin.json" in out
    git(repo.root, "add", "-A")
    assert main(["--root", str(repo.root), "precommit"]) == 0


def test_precommit_runs_check(repo, capsys):
    init(repo)
    repo.add_skill("dev", "foo", frontmatter={"name": "other", "description": "A test skill used by the toolkit tests. " + "x" * 20})
    main(["--root", str(repo.root), "build"])
    git(repo.root, "add", "-A")
    assert main(["--root", str(repo.root), "precommit"]) == 1
    assert "ERROR plugins/dev/skills/foo" in capsys.readouterr().out
