import shutil

import pytest

from sharron_support import add_row, git, load, make_clone, make_skill

ds = load("datasync")
ledger = load("ledger")
pytestmark = pytest.mark.usefixtures("isolated_git")
LEDGER = "ledger/costs.md"
MSG = "chore(sharron): record task cost [skip ci]"
SKILL_PATH = "plugins/workflow/skills/sharron"


def remote_ids(clone):
    text = git(clone, "show", f"origin/main:{SKILL_PATH}/{LEDGER}")
    # the git helper strips the final newline, which the strict ledger parser requires
    return [r["task_id"] for r in ledger.parse_ledger(text + "\n").tasks]


def test_commits_only_the_data_file_and_pushes(tmp_path):
    clone, skill = make_clone(tmp_path)
    (clone / "notes.txt").write_text("wip\n")
    git(clone, "add", "notes.txt")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (True, True, None)
    assert git(clone, "log", "-1", "--format=%s") == MSG
    assert git(clone, "show", "--name-only", "--format=", "HEAD") == f"{SKILL_PATH}/{LEDGER}"
    assert git(clone, "diff", "--cached", "--name-only") == "notes.txt"
    assert remote_ids(clone) == ["t-20261027-01"]


def test_other_branch_commits_without_pushing(tmp_path):
    clone, skill = make_clone(tmp_path)
    git(clone, "checkout", "-q", "-b", "feature")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (True, False, "not-on-default-branch")


def test_other_outgoing_commits_block_the_push(tmp_path):
    clone, skill = make_clone(tmp_path)
    (clone / "other.txt").write_text("x\n")
    git(clone, "add", "other.txt")
    git(clone, "commit", "-qm", "my own work")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.pushed, result.reason) == (False, "other-outgoing-commits")
    assert remote_ids(clone) == []


def test_ledger_rows_from_another_machine_are_kept(tmp_path):
    a_root, a = make_clone(tmp_path, "a")
    _, b = make_clone(tmp_path, "b")
    add_row(b, "t-20261027-01")
    assert ds.sync(b, LEDGER, MSG).pushed
    add_row(a, "t-20261027-02")
    assert ds.sync(a, LEDGER, MSG).pushed
    assert remote_ids(a_root) == ["t-20261027-01", "t-20261027-02"]


def test_other_conflicts_abort_the_rebase(tmp_path):
    a_root, a = make_clone(tmp_path, "a")
    _, b = make_clone(tmp_path, "b")
    message = "chore(sharron): update registry [skip ci]"
    (b / "registry.toml").write_text("schema_version = 1\n# from b\n")
    assert ds.sync(b, "registry.toml", message).pushed
    (a / "registry.toml").write_text("schema_version = 1\n# from a\n")
    result = ds.sync(a, "registry.toml", message)
    assert (result.committed, result.pushed, result.reason) == (True, False, "rebase-conflict")
    assert not (a_root / ".git/rebase-merge").exists() and git(a_root, "status", "--porcelain") == ""


def test_remote_ahead_with_dirty_tree_skips_push_and_keeps_wip(tmp_path):
    a_root, a = make_clone(tmp_path, "a")
    _, b = make_clone(tmp_path, "b")
    add_row(b, "t-20261027-01")
    ds.sync(b, LEDGER, MSG)
    (a_root / "README.md").write_text("work in progress\n")
    add_row(a, "t-20261027-02")
    result = ds.sync(a, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (True, False, "remote-ahead-dirty-tree")
    assert (a_root / "README.md").read_text() == "work in progress\n"
    assert git(a_root, "stash", "list") == ""


def test_outside_a_clone_the_notice_comes_once(tmp_path):
    skill = make_skill(tmp_path / "copy")
    first, second = ds.sync(skill, LEDGER, MSG), ds.sync(skill, LEDGER, MSG)
    assert (first.committed, first.reason) == (False, "not-a-clone")
    assert first.notice and second.notice is None


def test_staged_memory_blocks_the_push(tmp_path):
    clone, skill = make_clone(tmp_path)
    (clone / "MEMORY.md").write_text("x\n")
    git(clone, "add", "-f", "MEMORY.md")
    add_row(skill, "t-20261027-01")
    assert ds.sync(skill, LEDGER, MSG).reason == "memory-guard"


def test_fetch_failure_keeps_the_commit_local(tmp_path):
    _, skill = make_clone(tmp_path)
    shutil.rmtree(tmp_path / "remote.git")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (True, False, "fetch-failed")


@pytest.mark.parametrize("path,message", [
    ("config.toml", MSG), (LEDGER, "chore(sharron): no marker"), (LEDGER, "fix: x [skip ci]"),
])
def test_rejects_other_files_and_messages(tmp_path, path, message):
    with pytest.raises(ValueError):
        ds.sync(make_skill(tmp_path), path, message)


def test_the_same_row_on_both_machines_leaves_one_row(tmp_path):
    a_root, a = make_clone(tmp_path, "a")
    _, b = make_clone(tmp_path, "b")
    add_row(b, "t-20261027-01")
    assert ds.sync(b, LEDGER, MSG).pushed
    add_row(a, "t-20261027-01")
    result = ds.sync(a, LEDGER, MSG)
    assert (result.committed, result.reason) == (True, None)
    assert remote_ids(a_root) == ["t-20261027-01"]
    assert git(a_root, "status", "--porcelain") == ""


def test_write_atomic_uses_unix_newlines_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "state" / "x.txt"
    ds.write_atomic(target, "a\nb\n")
    ds.write_atomic(target, "c\n")
    assert target.read_bytes() == b"c\n"
    assert [p.name for p in target.parent.iterdir()] == ["x.txt"]


def test_cli_prints_the_result_and_rejects_bad_input(tmp_path, capsys):
    skill = make_skill(tmp_path / "copy")
    assert ds.main(["sync", LEDGER, "--message", MSG, "--skill-dir", str(skill)]) == 0
    assert '"reason": "not-a-clone"' in capsys.readouterr().out
    assert ds.main(["sync", "config.toml", "--message", MSG, "--skill-dir", str(skill)]) == 1
    assert capsys.readouterr().err.startswith("datasync.py: ")


def test_an_error_while_merging_the_ledger_leaves_no_rebase_behind(tmp_path, monkeypatch):
    a_root, a = make_clone(tmp_path, "a")
    _, b = make_clone(tmp_path, "b")
    add_row(b, "t-20261027-01")
    assert ds.sync(b, LEDGER, MSG).pushed
    add_row(a, "t-20261027-02")
    real = ds.write_atomic

    def broken(path, text):
        if path.name == "costs.md":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(ds, "write_atomic", broken)
    with pytest.raises(OSError):
        ds.sync(a, LEDGER, MSG)
    assert not (a_root / ".git/rebase-merge").exists()
    assert git(a_root, "branch", "--show-current") == "main"
    assert git(a_root, "status", "--porcelain") == ""


def test_detached_head_is_not_committed_into(tmp_path):
    clone, skill = make_clone(tmp_path)
    git(clone, "checkout", "-q", "--detach")
    add_row(skill, "t-20261027-01")
    before = git(clone, "rev-parse", "HEAD")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (False, False, "commit-failed")
    assert "detached" in result.detail
    assert git(clone, "rev-parse", "HEAD") == before and git(clone, "status", "--porcelain")


@pytest.mark.parametrize("marker,word", [("MERGE_HEAD", "merge"), ("BISECT_LOG", "bisect"), ("rebase-merge", "rebase")])
def test_an_operation_in_progress_blocks_the_commit(tmp_path, marker, word):
    clone, skill = make_clone(tmp_path)
    add_row(skill, "t-20261027-01")
    target = clone / ".git" / marker
    if marker == "rebase-merge":
        target.mkdir()
    else:
        target.write_text(git(clone, "rev-parse", "HEAD") + "\n")
    before = git(clone, "rev-parse", "HEAD")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (False, False, "commit-failed")
    assert word in result.detail
    assert git(clone, "rev-parse", "HEAD") == before
    assert "costs.md" in git(clone, "status", "--porcelain")


def test_a_copy_inside_another_repo_never_commits_or_pushes_there(tmp_path):
    remote = tmp_path / "project.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    project = tmp_path / "proj"
    git(tmp_path, "clone", "-q", str(remote), str(project))
    (project / "app.py").write_text("print('hi')\n")
    git(project, "add", "app.py")
    git(project, "commit", "-qm", "initial")
    git(project, "push", "-q", "-u", "origin", "main")
    skill = shutil.copytree(make_skill(tmp_path / "src"), project / ".agents/skills/sharron")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "add the skill")
    git(project, "push", "-q")
    remote_before, local_before = git(remote, "rev-parse", "main"), git(project, "rev-parse", "HEAD")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (False, False, "not-a-clone")
    assert result.notice
    assert git(project, "rev-parse", "HEAD") == local_before
    assert git(remote, "rev-parse", "main") == remote_before
    assert git(project, "diff", "--cached", "--name-only") == ""


def test_ssh_runs_in_batch_mode_and_keeps_the_users_command(tmp_path, monkeypatch):
    clone, skill = make_clone(tmp_path)
    log = tmp_path / "ssh.log"
    fake_ssh = tmp_path / "fake-ssh"
    fake_ssh.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 1\n')
    fake_ssh.chmod(0o755)
    monkeypatch.setenv("GIT_SSH_COMMAND", f"{fake_ssh} -o ConnectTimeout=5")
    git(clone, "remote", "set-url", "origin", "ssh://git.example.invalid/repo.git")
    add_row(skill, "t-20261027-01")
    result = ds.sync(skill, LEDGER, MSG)
    assert (result.committed, result.pushed, result.reason) == (True, False, "fetch-failed")
    assert "-o ConnectTimeout=5 -o BatchMode=yes" in log.read_text()


def test_batch_mode_is_added_to_core_ssh_command_or_plain_ssh(tmp_path, monkeypatch):
    clone, skill = make_clone(tmp_path)
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.delenv("GIT_SSH", raising=False)
    assert ds._batch_ssh_env(skill) == {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}
    git(clone, "config", "core.sshCommand", "ssh -i keyfile")
    assert ds._batch_ssh_env(skill) == {"GIT_SSH_COMMAND": "ssh -i keyfile -o BatchMode=yes"}
