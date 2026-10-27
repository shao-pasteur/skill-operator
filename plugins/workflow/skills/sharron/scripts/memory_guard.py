#!/usr/bin/env python3
"""Keep MEMORY.md out of git, and create it with its section skeleton.

Usage (from the skill folder):
    sh scripts/run.sh memory_guard.py check [--cwd DIR]       exclude MEMORY.md from git, then create or extend it
    sh scripts/run.sh memory_guard.py precommit [--cwd DIR]   look for MEMORY.md in the staged changes or in unpushed commits

Both print one JSON object. `check` exits 1 when git already tracks MEMORY.md (status "tracked": nothing is
written); `precommit` exits 1 when MEMORY.md is staged or in an unpushed commit (status "blocked").
MEMORY.md lives in the workspace root: the top of the git work tree, or the current folder outside git.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

MARKER = "<!-- sharron memory — never commit this file -->"
FILE_NAME = "MEMORY.md"
SECTIONS = "## 偏好與教訓\n\n## 任務紀錄\n"
TRACKED_NOTICE = (
    "MEMORY.md is tracked by git, so sharron will not write to it. "
    "To untrack it and keep the file, run: git rm --cached MEMORY.md"
)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in cwd; a missing git program counts as a failed command."""
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as error:
        return subprocess.CompletedProcess(["git", *args], 127, "", str(error))


def workspace_root(cwd: Path) -> Path:
    """Top of the git work tree that holds cwd, or cwd itself when it is not in a repo."""
    result = _git(cwd, "rev-parse", "--show-toplevel")
    top = result.stdout.strip()
    return Path(top) if result.returncode == 0 and top else cwd


def _in_repo(root: Path) -> bool:
    return _git(root, "rev-parse", "--show-toplevel").returncode == 0


def _exclude_path(root: Path) -> Path:
    """The shared .git/info/exclude file: relative to root in a normal repo, absolute in a linked worktree."""
    printed = Path(_git(root, "rev-parse", "--git-path", "info/exclude").stdout.strip())
    return printed if printed.is_absolute() else root / printed


def _add_exclusion(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{separator}/{FILE_NAME}\n")


def _write_skeleton(memory: Path) -> tuple[bool, bool]:
    """Create MEMORY.md, or append the skeleton when it has no marker. Returns (created, appended_sections)."""
    if not memory.exists():
        memory.write_text(f"# MEMORY\n\n{MARKER}\n\n{SECTIONS}", encoding="utf-8")
        return True, False
    text = memory.read_text(encoding="utf-8")
    if MARKER in text:
        return False, False
    separator = "" if text.endswith("\n") else "\n"
    memory.write_text(f"{text}{separator}\n{MARKER}\n\n{SECTIONS}", encoding="utf-8")
    return False, True


def check(cwd: Path) -> dict:
    root = workspace_root(cwd)
    memory = root / FILE_NAME
    result = {
        "memory_path": str(memory),
        "git": _in_repo(root),
        "status": "ok",
        "created": False,
        "appended_sections": False,
        "notice": None,
    }
    if result["git"]:
        if _git(root, "ls-files", "--error-unmatch", "--", FILE_NAME).returncode == 0:
            result["status"] = "tracked"
            result["notice"] = TRACKED_NOTICE
            return result
        if _git(root, "check-ignore", "-q", "--", FILE_NAME).returncode != 0:
            exclude = _exclude_path(root)
            _add_exclusion(exclude)
            result["status"] = "excluded"
            result["notice"] = f"Added {FILE_NAME} to {exclude} so git ignores it (local only)."
    result["created"], result["appended_sections"] = _write_skeleton(memory)
    return result


def precommit(cwd: Path) -> dict:
    root = workspace_root(cwd)
    if not _in_repo(root):
        return {"status": "no-git", "staged": False, "outgoing": []}
    staged = bool(_git(root, "diff", "--cached", "--name-only", "--diff-filter=d", "--", FILE_NAME).stdout.strip())
    log = _git(root, "log", "--format=%H", "--diff-filter=d", "HEAD", "--not", "--remotes", "--", FILE_NAME)
    outgoing = log.stdout.split() if log.returncode == 0 else []  # no commits yet: nothing can be outgoing
    return {"status": "blocked" if staged or outgoing else "ok", "staged": staged, "outgoing": outgoing}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory_guard.py", description="Keep MEMORY.md out of git.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("check", "exclude MEMORY.md from git, then create or extend it"),
        ("precommit", "report MEMORY.md in the staged changes or in unpushed commits"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--cwd", type=Path, default=Path("."), help="a folder inside the workspace (default: .)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check(args.cwd) if args.command == "check" else precommit(args.cwd)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] in ("tracked", "blocked") else 0


if __name__ == "__main__":
    sys.exit(main())
