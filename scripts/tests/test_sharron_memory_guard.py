import pytest

from sharron_support import git, load

mg = load("memory_guard")
pytestmark = pytest.mark.usefixtures("isolated_git")


def repo(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    git(root, "init", "-q")
    (root / "a.txt").write_text("a\n")
    git(root, "add", "a.txt")
    git(root, "commit", "-qm", "init")
    return root


def track_memory_and_push(tmp_path):
    root = repo(tmp_path)
    git(tmp_path, "init", "-q", "--bare", "remote.git")
    git(root, "remote", "add", "origin", str(tmp_path / "remote.git"))
    (root / "MEMORY.md").write_text("mine\n")
    git(root, "add", "-f", "MEMORY.md")
    git(root, "commit", "-qm", "track memory")
    git(root, "push", "-q", "-u", "origin", "main")
    return root


def test_not_a_git_repo_creates_the_skeleton(tmp_path):
    result = mg.check(tmp_path)
    assert (result["git"], result["status"], result["created"]) == (False, "ok", True)
    text = (tmp_path / "MEMORY.md").read_text()
    assert text.startswith("# MEMORY\n") and mg.MARKER in text and "## 偏好與教訓" in text and "## 任務紀錄" in text


def test_untracked_memory_is_excluded_once(tmp_path):
    root = repo(tmp_path)
    (root / "src").mkdir()
    first, second = mg.check(root / "src"), mg.check(root)
    assert first["memory_path"] == str(root / "MEMORY.md")
    assert (first["status"], second["status"]) == ("excluded", "ok")
    assert first["notice"] and second["notice"] is None
    assert (root / ".git/info/exclude").read_text().count("/MEMORY.md") == 1
    assert git(root, "status", "--porcelain") == ""


def test_already_ignored_memory_is_left_alone(tmp_path):
    root = repo(tmp_path)
    (root / ".gitignore").write_text("MEMORY.md\n")
    git(root, "add", ".gitignore")
    git(root, "commit", "-qm", "ignore")
    assert mg.check(root)["status"] == "ok"
    exclude = root / ".git/info/exclude"
    assert not exclude.exists() or "/MEMORY.md" not in exclude.read_text()


def test_tracked_memory_is_blocked_and_untouched(tmp_path):
    root = track_memory_and_push(tmp_path)
    result = mg.check(root)
    assert result["status"] == "tracked" and "git rm --cached MEMORY.md" in result["notice"]
    assert (root / "MEMORY.md").read_text() == "mine\n"
    assert mg.main(["check", "--cwd", str(root)]) == 1


def test_worktree_writes_the_shared_exclude_file(tmp_path):
    root = repo(tmp_path)
    git(root, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feature")
    result = mg.check(tmp_path / "wt")
    assert result["status"] == "excluded" and result["memory_path"] == str(tmp_path / "wt" / "MEMORY.md")
    assert "/MEMORY.md" in (root / ".git/info/exclude").read_text()
    assert git(tmp_path / "wt", "status", "--porcelain") == ""


def test_existing_memory_without_marker_keeps_its_content(tmp_path):
    (tmp_path / "MEMORY.md").write_text("# My notes\n- keep me\n")
    first, second = mg.check(tmp_path), mg.check(tmp_path)
    text = (tmp_path / "MEMORY.md").read_text()
    assert text.startswith("# My notes\n- keep me\n") and text.count(mg.MARKER) == 1
    assert (first["appended_sections"], second["appended_sections"]) == (True, False)


def test_precommit_catches_staged_memory(tmp_path):
    root = repo(tmp_path)
    mg.check(root)
    git(root, "add", "-f", "MEMORY.md")
    result = mg.precommit(root)
    assert (result["status"], result["staged"]) == ("blocked", True)


def test_precommit_catches_outgoing_memory(tmp_path):
    root = repo(tmp_path)
    (root / "MEMORY.md").write_text("x\n")
    git(root, "add", "-f", "MEMORY.md")
    git(root, "commit", "-qm", "oops")
    result = mg.precommit(root)
    assert result["status"] == "blocked" and result["outgoing"] == [git(root, "rev-parse", "HEAD")]


def test_precommit_allows_the_untracking_commit(tmp_path):
    root = track_memory_and_push(tmp_path)
    git(root, "rm", "-q", "--cached", "MEMORY.md")
    assert mg.precommit(root)["status"] == "ok"
    git(root, "commit", "-qm", "untrack memory")
    assert mg.precommit(root)["status"] == "ok"
