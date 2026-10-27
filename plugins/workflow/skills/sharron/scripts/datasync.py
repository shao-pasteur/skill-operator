#!/usr/bin/env python3
"""Commit one sharron data file and push it, only when that is safe (the "data sync" procedure).

Usage (from the skill folder):
    sh scripts/run.sh datasync.py sync <rel_path> --message "<msg>"

<rel_path> is ledger/costs.md, security-references.toml or registry.toml, relative to the skill folder.
<msg> starts with "chore(sharron): " and contains "[skip ci]". Prints one JSON object:
{"committed", "pushed", "reason", "detail", "notice"}. A reason is not an error: the data stays committed
(or in the working tree) and the next sync tries again. The scripts never use --no-verify or a force push.

Also provides the helpers the other scripts share: write_atomic, file_lock and notice_once.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import contextlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from dataclasses import asdict, dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import ledger  # noqa: E402
import memory_guard  # noqa: E402

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

DATA_FILES = ("ledger/costs.md", "security-references.toml", "registry.toml")
LEDGER_FILE = DATA_FILES[0]
MESSAGE_PREFIX = "chore(sharron): "
SKIP_CI = "[skip ci]"
NOT_A_CLONE_NOTICE = (
    "This copy of sharron is not a git clone, so ledger rows and reference updates stay here and never reach "
    "the repo. Install it from a local clone to keep them."
)
NETWORK_TIMEOUT = 120  # seconds for fetch and push, so an unreachable remote cannot hang a task
MAX_REBASE_STEPS = 100
IN_PROGRESS = (  # a file under the git directory, and what its presence means
    ("rebase-merge", "a rebase is in progress"),
    ("rebase-apply", "a rebase or am is in progress"),
    ("MERGE_HEAD", "a merge is in progress"),
    ("CHERRY_PICK_HEAD", "a cherry-pick is in progress"),
    ("REVERT_HEAD", "a revert is in progress"),
    ("BISECT_LOG", "a bisect is in progress"),
)


@dataclass(frozen=True)
class SyncResult:
    committed: bool
    pushed: bool
    reason: str | None = None
    detail: str | None = None
    notice: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


def write_atomic(path: Path, text: str) -> None:
    """Write text to path as UTF-8 with \\n line endings: a temp file in the same folder, fsynced, then renamed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copymode(path, temp)
        else:
            os.chmod(temp, 0o644)
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


@contextlib.contextmanager
def file_lock(skill_dir: Path, name: str) -> Iterator[None]:
    """Hold an exclusive lock on state/<name>.lock until the block ends (flock, or msvcrt on Windows)."""
    lock_path = skill_dir / "state" / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle, fcntl.LOCK_EX)
        else:  # msvcrt.locking gives up after about ten seconds, so retry until it succeeds
            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
            else:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def notice_once(skill_dir: Path, key: str, message: str) -> str | None:
    """Return message the first time key is seen and None afterwards; shown keys live in state/notices.json."""
    path = skill_dir / "state" / "notices.json"
    with file_lock(skill_dir, "notices"):
        try:
            shown = json.loads(path.read_text(encoding="utf-8"))["shown"]
            if not isinstance(shown, list):
                shown = []
        except (OSError, ValueError, KeyError, TypeError):
            shown = []
        if key in shown:
            return None
        write_atomic(path, json.dumps({"shown": [*shown, key]}, indent=2) + "\n")
        return message


def _git(skill_dir: Path, *args: str, timeout: float | None = None, env: dict[str, str] | None = None):
    """Run `git -C skill_dir ...`; a missing git program or a timeout counts as a failed command."""
    command = ["git", "-C", str(skill_dir), *args]
    full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    try:
        return subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=False, timeout=timeout, env=full_env,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _last_line(result: subprocess.CompletedProcess[str]) -> str | None:
    lines = [line.strip() for line in (result.stderr + "\n" + result.stdout).splitlines() if line.strip()]
    return lines[-1] if lines else None


def _check_arguments(rel_path: str, message: str) -> None:
    if rel_path not in DATA_FILES:
        raise ValueError(f"{rel_path!r} is not a sharron data file; allowed: {', '.join(DATA_FILES)}")
    if not message.startswith(MESSAGE_PREFIX):
        raise ValueError(f"the commit message must start with {MESSAGE_PREFIX!r}")
    if SKIP_CI not in message:
        raise ValueError(f"the commit message must contain {SKIP_CI!r}")


def _commit(skill_dir: Path, rel_path: str, message: str) -> tuple[bool, str | None]:
    """Commit rel_path alone when it differs from HEAD. Returns (a commit was made, the failure line or None)."""
    if (skill_dir / rel_path).exists() and _git(skill_dir, "ls-files", "--error-unmatch", "--", rel_path).returncode:
        added = _git(skill_dir, "add", "--", rel_path)  # a new file: the pathspec commit needs it in the index
        if added.returncode:
            return False, _last_line(added) or "git add failed"
    if _git(skill_dir, "diff", "--quiet", "HEAD", "--", rel_path).returncode == 0:
        return False, None
    result = _git(skill_dir, "commit", "-m", message, "--", rel_path)
    if result.returncode:
        return False, _last_line(result) or "git commit failed"
    return True, None


def _outgoing_is_only_data(skill_dir: Path, commits: list[str]) -> bool:
    prefix = _git(skill_dir, "rev-parse", "--show-prefix").stdout.strip()
    allowed = {prefix + path for path in DATA_FILES}
    for sha in commits:
        parents = _git(skill_dir, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        subject = _git(skill_dir, "log", "-1", "--format=%s", sha).stdout.strip()
        files = _git(skill_dir, "diff-tree", "--root", "-r", "--no-commit-id", "--name-only", "-z", sha)
        touched = {name for name in files.stdout.split("\0") if name}
        if len(parents) > 2 or not subject.startswith(MESSAGE_PREFIX) or files.returncode or not touched <= allowed:
            return False
    return True


def _conflicted(skill_dir: Path) -> list[str]:
    out = _git(skill_dir, "diff", "--name-only", "--diff-filter=U", "-z").stdout
    return [name for name in out.split("\0") if name]


def _resolve_ledger(skill_dir: Path, ledger_path: str) -> bool:
    """Merge both ledger sides into the working file and stage it; False when the sides cannot be merged."""
    upstream = _git(skill_dir, "show", f":2:{ledger_path}")
    local = _git(skill_dir, "show", f":3:{ledger_path}")
    if upstream.returncode or local.returncode:
        return False
    try:
        merged = ledger.merge_ledgers(upstream.stdout, local.stdout)
    except ValueError:  # LedgerError, or a number the parser cannot handle
        return False
    write_atomic(skill_dir / LEDGER_FILE, merged)
    return _git(skill_dir, "add", "--", LEDGER_FILE).returncode == 0


def _rebase(skill_dir: Path, upstream: str) -> SyncResult | None:
    """Rebase onto upstream, merging ledger conflicts; abort and return a result for any other conflict."""
    env = {"GIT_EDITOR": "true"}
    prefix = _git(skill_dir, "rev-parse", "--show-prefix").stdout.strip()
    ledger_path = prefix + LEDGER_FILE
    step = _git(skill_dir, "rebase", upstream, env=env)
    try:
        for _ in range(MAX_REBASE_STEPS):
            if step.returncode == 0:
                return None
            conflicts = _conflicted(skill_dir)
            if conflicts != [ledger_path] or not _resolve_ledger(skill_dir, ledger_path):
                detail = ", ".join(conflicts) if conflicts else _last_line(step)
                _git(skill_dir, "rebase", "--abort")
                return SyncResult(True, False, "rebase-conflict", detail)
            step = _git(skill_dir, "rebase", "--continue", env=env)
    except BaseException:  # never leave the user's clone in the middle of a rebase
        _git(skill_dir, "rebase", "--abort")
        raise
    _git(skill_dir, "rebase", "--abort")
    return SyncResult(True, False, "rebase-conflict", "the rebase did not finish")


def _operation_in_progress(skill_dir: Path) -> str | None:
    """Name the git operation that owns HEAD right now (so sync must not commit into it), or None."""
    for name, description in IN_PROGRESS:
        printed = _git(skill_dir, "rev-parse", "--git-path", name).stdout.strip()
        if printed and (skill_dir / printed).exists():
            return description
    if _git(skill_dir, "symbolic-ref", "--quiet", "HEAD").returncode:
        return "HEAD is detached"
    return None


def sync(skill_dir: Path, rel_path: str, message: str) -> SyncResult:
    """Commit rel_path (only that file) and push it when every safeguard allows; see the module docstring."""
    _check_arguments(rel_path, message)
    if _git(skill_dir, "rev-parse", "--is-inside-work-tree").returncode:
        return SyncResult(False, False, "not-a-clone", None, notice_once(skill_dir, "not-a-clone", NOT_A_CLONE_NOTICE))

    busy = _operation_in_progress(skill_dir)
    if busy:  # committing now would land inside the user's operation; the row stays for the next sync
        return SyncResult(False, False, "commit-failed", busy)
    committed, failure = _commit(skill_dir, rel_path, message)
    if failure:
        return SyncResult(False, False, "commit-failed", failure)

    def stop(reason: str, detail: str | None = None) -> SyncResult:
        return SyncResult(committed, False, reason, detail)

    branch = _git(skill_dir, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    configured = _git(skill_dir, "config", f"branch.{branch}.remote").stdout.strip() if branch else ""
    remote = configured or "origin"
    head = _git(skill_dir, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD")
    default = head.stdout.strip().removeprefix(f"{remote}/") if head.returncode == 0 else "main"
    if not branch or branch != (default or "main"):
        return stop("not-on-default-branch")

    upstream = _git(skill_dir, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode:
        return stop("no-upstream")
    fetch = _git(skill_dir, "fetch", "--quiet", remote, timeout=NETWORK_TIMEOUT)
    if fetch.returncode:
        return stop("fetch-failed", _last_line(fetch))

    outgoing = _git(skill_dir, "rev-list", "--reverse", "@{u}..HEAD").stdout.split()
    if not outgoing:
        return SyncResult(committed, False)
    if not _outgoing_is_only_data(skill_dir, outgoing):
        return stop("other-outgoing-commits")

    if int(_git(skill_dir, "rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0) > 0:
        if _git(skill_dir, "status", "--porcelain", "--untracked-files=no").stdout.strip():
            return stop("remote-ahead-dirty-tree")
        failed = _rebase(skill_dir, "@{u}")
        if failed:
            return failed

    top = _git(skill_dir, "rev-parse", "--show-toplevel").stdout.strip()
    guard = memory_guard.precommit(Path(top))
    if guard["status"] != "ok":
        return stop("memory-guard", guard["status"])

    target = upstream.stdout.strip().removeprefix(f"{remote}/")
    pushed = _git(skill_dir, "push", "--quiet", remote, f"HEAD:{target}", timeout=NETWORK_TIMEOUT)
    if pushed.returncode:
        return stop("push-failed", _last_line(pushed))
    return SyncResult(committed, True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datasync.py", description="Commit and push one sharron data file.")
    commands = parser.add_subparsers(dest="command", required=True)
    sync_parser = commands.add_parser("sync", help="commit one data file and push it when that is safe")
    sync_parser.add_argument("rel_path", help=f"one of: {', '.join(DATA_FILES)}")
    sync_parser.add_argument("--message", required=True, help=f'commit message: "{MESSAGE_PREFIX}..." with "{SKIP_CI}"')
    sync_parser.add_argument("--skill-dir", type=Path, default=Path(__file__).resolve().parent.parent)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = sync(args.skill_dir, args.rel_path, args.message)
    except ValueError as error:
        print(f"datasync.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_json(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
