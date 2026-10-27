#!/usr/bin/env python3
"""Keep one redacted trace file per task: its brief, its report and its decisions.

Usage (from the skill folder; every subcommand prints one JSON object):
    echo '{"goal": "..."}' | sh scripts/run.sh trace.py append --task-id ID --kind brief|report|decision
    sh scripts/run.sh trace.py prune

`append` reads a JSON object on stdin, redacts it and adds one line to state/traces/<task-id>.jsonl; it
prints {"path": ...}. Secrets (keys, tokens, passwords, private keys) become [REDACTED], and personal
home paths are rewritten, because the skill folder is scanned for them by the repo checks whether or
not state/ is gitignored. Starting a new task file also runs `prune`, which keeps the newest 50 traces
younger than 30 days and prints {"removed": [task ids]}. Bad input prints one line on stderr and exits 1.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import config  # noqa: E402

KINDS = ("brief", "report", "decision")
TRACE_DIR = "state/traces"

_SECRET_KEYS = frozenset((
    "password", "passwd", "secret", "token", "access_token", "refresh_token", "api_key", "apikey",
    "authorization", "cookie", "private_key", "client_secret",
))

# Applied to every string in this order (see redact()).
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.DOTALL)
_TOKEN_RES = [
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
]
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s\"']{8,}")
_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|client[_-]?secret"
    r"|password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]+)"
)
# The same shapes the repo validator looks for; the replacements contain "<", which these never match.
# The patterns are assembled from parts so this file itself does not look like a personal path to that validator.
_NAME = r"[^/\s<>\"'`]+"
_OTHER_HOME_RES = [
    (re.compile("/Users/" + _NAME), "/Users/<user>"),
    (re.compile("/home/" + _NAME), "/home/<user>"),
    (re.compile(r"(?i)C:\\{1,2}Users\\{1,2}[^\\\s<>\"']+"), lambda _match: "C:\\Users\\<user>"),
]


def _redact_text(text: str, home: str) -> str:
    text = _PEM_RE.sub("[REDACTED PRIVATE KEY]", text)
    for pattern in _TOKEN_RES:
        text = pattern.sub("[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _ASSIGNMENT_RE.sub(lambda m: m.group(1) + "[REDACTED]", text)
    home = home.rstrip("/\\")
    if home:
        text = re.sub(re.escape(home) + r"(?=/|$)", "~", text)
    for pattern, replacement in _OTHER_HOME_RES:
        text = pattern.sub(replacement, text)
    return text


def redact(value: object, home: str) -> object:
    """Return a copy of value (walking dicts, lists and strings) with secrets and home paths removed."""
    if isinstance(value, dict):
        return {
            (_redact_text(key, home) if isinstance(key, str) else key): (
                "[REDACTED]" if isinstance(key, str) and key.lower() in _SECRET_KEYS else redact(item, home)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, home) for item in value]
    if isinstance(value, str):
        return _redact_text(value, home)
    return value


def append(
    skill_dir: Path, task_id: str, kind: str, payload: dict,
    now: datetime | None = None, home: str | None = None,
) -> Path:
    """Add one redacted line to the task's trace file and return its path; prune when the file is new."""
    if not isinstance(task_id, str) or not config.TASK_ID_RE.fullmatch(task_id):  # fullmatch: `$` accepts a trailing newline
        raise ValueError(f"task id '{task_id}' must look like t-20261027-01")
    if kind not in KINDS:
        raise ValueError(f"kind '{kind}' must be one of {', '.join(KINDS)}")
    if not isinstance(payload, dict):
        raise ValueError("the payload must be a JSON object")
    now = now or datetime.now(timezone.utc)
    home = os.path.expanduser("~") if home is None else home
    line = json.dumps({"ts": now.isoformat(), "kind": kind, "payload": redact(payload, home)}, ensure_ascii=False)
    path = Path(skill_dir) / TRACE_DIR / f"{task_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if is_new:
        prune(skill_dir, now=now)
    return path


def prune(skill_dir: Path, now: datetime | None = None, keep: int = 50, max_age_days: int = 30) -> list[str]:
    """Delete traces beyond the `keep` newest or older than max_age_days; return the removed task ids, sorted."""
    folder = Path(skill_dir) / TRACE_DIR
    if not folder.is_dir():
        return []
    now = now or datetime.now(timezone.utc)
    oldest_allowed = (now - timedelta(days=max_age_days)).timestamp()
    files = sorted(((p.stat().st_mtime, p.name, p) for p in folder.glob("*.jsonl")), reverse=True)
    removed = []
    for position, (modified, _name, path) in enumerate(files):
        if position >= keep or modified < oldest_allowed:
            try:
                path.unlink()
            except OSError:
                continue  # a trace we cannot delete must not fail the append that triggered the prune
            removed.append(path.stem)
    return sorted(removed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trace.py", description="Keep redacted per-task traces.")
    parser.add_argument(
        "--skill-dir", type=Path, default=config.DEFAULT_SKILL_DIR, help="skill folder (default: the folder above scripts/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("append", help="add the JSON object on stdin to a task's trace")
    add.add_argument("--task-id", required=True)
    add.add_argument("--kind", required=True, help="one of " + ", ".join(KINDS))
    sub.add_parser("prune", help="delete old traces")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "append":
            result = {"path": str(append(args.skill_dir, args.task_id, args.kind, json.loads(sys.stdin.read())))}
        else:
            result = {"removed": prune(args.skill_dir)}
    except (ValueError, OSError) as error:  # JSONDecodeError is a ValueError
        print(f"trace.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
