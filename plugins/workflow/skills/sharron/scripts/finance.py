#!/usr/bin/env python3
"""Measure what a task cost, suggest a budget for the next one, and keep the cost ledger.

Usage (from the skill folder; every subcommand prints one JSON object):
    sh scripts/run.sh finance.py suggest --platform P --playbook PB --difficulty N
    sh scripts/run.sh finance.py usage --platform P --since ISO [--budget USD] [--session-id ID]
                                       [--agents IDS | --exclude-agents IDS]
    sh scripts/run.sh finance.py record --platform P --task-id ID --since ISO --playbook PB --domain D
                                        --difficulty N --subagents N --outcome O --verified C/N
                                        [--session-id ID] [--agents IDS | --exclude-agents IDS]
                                        [--input-tokens N --output-tokens N --cache-tokens N --cost-usd USD]
                                        [--models LIST]
    sh scripts/run.sh finance.py correct --task-id ID

Only Claude Code is measured, from its session transcripts: this reads type, timestamp, requestId,
message.id, message.model and message.usage of each line, never the message content. Other platforms
record `unknown` unless the usage is passed on the command line. Prices come from `[prices]` in the
settings (equivalent USD per million tokens); a model without a price makes the cost `unknown`.
`record` and `correct` append to ledger/costs.md and then run the data sync (datasync.py).
Bad input prints one line on stderr and exits 1.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
from collections.abc import Mapping  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import config  # noqa: E402
import datasync  # noqa: E402
import ledger as ledger_format  # noqa: E402
from ledger import Ledger, LedgerError  # noqa: E402

RECORD_MESSAGE = "chore(sharron): record task cost [skip ci]"
CORRECTION_MESSAGE = "chore(sharron): record task correction [skip ci]"
ENV_CLAUDE_DIR = "CLAUDE_CONFIG_DIR"
ENV_SESSION = "CLAUDE_CODE_SESSION_ID"
AGENT_PREFIX = "agent-"
P80_MIN_TASKS = 5  # tasks with the same difficulty
REGRESSION_MIN_TASKS = 10  # tasks in the playbook
CONCRETE_PLATFORMS = tuple(p for p in config.PLATFORMS if p != "auto")
_SAFE_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")


@dataclass
class ModelUsage:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


@dataclass(frozen=True)
class Suggestion:
    budget_usd: float
    method: str  # "p80", "regression" or "default"
    n: int  # the tasks the suggestion rests on; 0 for the default


# ---------------------------------------------------------------- transcripts


def encode_workspace(cwd: Path) -> str:
    """The folder name Claude Code gives a workspace under projects/."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def _subagent_files(project_dirs: list[Path], session_id: str) -> list[Path]:
    found: list[Path] = []
    for folder in project_dirs:
        found += (folder / session_id / "subagents").glob(f"{AGENT_PREFIX}*.jsonl")
    return sorted(found)


def transcript_files(
    claude_dir: Path,
    session_id: str | None,
    cwd: Path,
    *,
    agents: frozenset[str] | None = None,
    exclude_agents: frozenset[str] = frozenset(),
) -> list[Path]:
    """The main transcript and the subagent transcripts of one session; [] when none is found.

    With a session id the main transcript is the first projects/*/<id>.jsonl. Without one it is the newest
    transcript of the workspace folder for cwd. `agents` keeps only those subagents and drops the main
    transcript; `exclude_agents` drops those subagents.
    """
    projects = claude_dir / "projects"
    if session_id:
        if not _SAFE_NAME_RE.fullmatch(session_id):
            return []
        project_dirs = sorted(p for p in projects.glob("*") if p.is_dir())
        mains = [p / f"{session_id}.jsonl" for p in project_dirs if (p / f"{session_id}.jsonl").is_file()]
        main = mains[0] if mains else None
    else:
        workspace = projects / encode_workspace(cwd)
        candidates = sorted(workspace.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if workspace.is_dir() else []
        main = candidates[-1] if candidates else None
        session_id = main.stem if main else None
        project_dirs = [workspace]
    if session_id is None:
        return []
    subagents = _subagent_files(project_dirs, session_id)

    def agent_id(path: Path) -> str:
        return path.stem[len(AGENT_PREFIX):]

    if agents is not None:
        subagents = [p for p in subagents if agent_id(p) in agents]
        main = None
    subagents = [p for p in subagents if agent_id(p) not in exclude_agents]
    return ([main] if main else []) + subagents


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _local_aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.astimezone()  # a naive time is local time


def sum_usage(files: list[Path], since: datetime) -> dict[str, ModelUsage]:
    """Add up the token usage of the assistant messages at or after `since`, per model.

    Lines that do not parse (a half-written last line) are skipped, and each (message id, request id)
    counts once. Models whose four counts are all 0 are left out.
    """
    start = _local_aware(since)
    seen: set[tuple[str, str]] = set()
    totals: dict[str, ModelUsage] = {}
    for path in files:
        try:
            handle = path.open(encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for text in handle:
                try:
                    entry = json.loads(text)
                    if entry.get("type") != "assistant":
                        continue
                    stamp = _local_aware(datetime.fromisoformat(entry["timestamp"]))
                    message = entry["message"]
                    model, usage = message["model"], message["usage"]
                    key = (message.get("id"), entry.get("requestId"))
                    counts = ModelUsage(
                        _count(usage.get("input_tokens")), _count(usage.get("output_tokens")),
                        _count(usage.get("cache_creation_input_tokens")), _count(usage.get("cache_read_input_tokens")),
                    )
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if stamp < start or not isinstance(model, str):
                    continue
                if key != (None, None):
                    if key in seen:
                        continue
                    seen.add(key)
                total = totals.setdefault(model, ModelUsage())
                total.input += counts.input
                total.output += counts.output
                total.cache_write += counts.cache_write
                total.cache_read += counts.cache_read
    return {m: u for m, u in totals.items() if u.input or u.output or u.cache_write or u.cache_read}


def price_usage(usage: dict[str, ModelUsage], prices: dict) -> tuple[float | None, list[str]]:
    """The equivalent USD cost, or None when a model has no price, plus the sorted models without one."""
    missing = sorted(model for model in usage if not isinstance(prices.get(model), dict))
    if missing:
        return None, missing
    total = 0.0
    for model, used in usage.items():
        p = prices[model]
        total += used.input * p["input"] + used.output * p["output"]
        total += used.cache_write * p["cache_write"] + used.cache_read * p["cache_read"]
    return total / 1e6, []


# ---------------------------------------------------------------- budget suggestion


def suggest_budget(
    ledger: Ledger, platform: str, playbook: str, difficulty: int, defaults: Mapping[str, float]
) -> Suggestion:
    """p80 of at least 5 same-difficulty tasks, else a regression over at least 10 tasks, else the default."""
    rows = [
        r for r in ledger_format.successful_rows(ledger)
        if r["platform"] == platform and r["playbook"] == playbook
    ]
    same = [float(r["cost_usd"]) for r in rows if int(r["difficulty"]) == difficulty]
    if len(same) >= P80_MIN_TASKS:
        return Suggestion(round(ledger_format.p80(same), 4), "p80", len(same))
    if len(rows) >= REGRESSION_MIN_TASKS:
        costs = [float(r["cost_usd"]) for r in rows]
        try:
            slope, intercept = statistics.linear_regression([float(r["difficulty"]) for r in rows], costs)
        except statistics.StatisticsError:  # every task has the same difficulty
            pass
        else:
            return Suggestion(round(max(slope * difficulty + intercept, min(costs)), 4), "regression", len(rows))
    return Suggestion(round(float(defaults[str(difficulty)]), 4), "default", 0)


# ---------------------------------------------------------------- the ledger file


def _read_ledger(skill_dir: Path) -> Ledger:
    path = skill_dir / datasync.LEDGER_FILE
    return ledger_format.parse_ledger(path.read_text(encoding="utf-8")) if path.exists() else Ledger([], [])


def _write_ledger(skill_dir: Path, current: Ledger) -> None:
    datasync.write_atomic(skill_dir / datasync.LEDGER_FILE, ledger_format.render_ledger(current))


def record(skill_dir: Path, row: dict[str, str]) -> dict:
    """Append one task row to the ledger and run the data sync."""
    ledger_format.validate_task_row(row)
    with datasync.file_lock(skill_dir, "ledger"):
        current = _read_ledger(skill_dir)
        if any(t["task_id"] == row["task_id"] for t in current.tasks):
            raise LedgerError(f"task {row['task_id']} is already recorded")
        current.tasks.append(dict(row))
        _write_ledger(skill_dir, current)
    return {"row": row, "sync": datasync.sync(skill_dir, datasync.LEDGER_FILE, RECORD_MESSAGE).to_json()}


def correct(skill_dir: Path, task_id: str, today: date) -> dict:
    """Mark a recorded task as wrong, so the summary and the suggestions leave it out, and run the data sync."""
    with datasync.file_lock(skill_dir, "ledger"):
        current = _read_ledger(skill_dir)
        if not any(t["task_id"] == task_id for t in current.tasks):
            raise LedgerError(f"task {task_id} is not in the ledger")
        entry = {"task_id": task_id, "date": today.isoformat()}
        if entry not in current.corrections:
            current.corrections.append(entry)
            _write_ledger(skill_dir, current)
    return {"row": entry, "sync": datasync.sync(skill_dir, datasync.LEDGER_FILE, CORRECTION_MESSAGE).to_json()}


# ---------------------------------------------------------------- command line


@dataclass
class Measurement:
    measurement: str  # "measured" or "unknown"
    input: int | None = None
    output: int | None = None
    cache: int | None = None
    cost: float | None = None
    models: list[str] | None = None
    unpriced: list[str] | None = None


def _ids(text: str | None) -> frozenset[str] | None:
    return None if text is None else frozenset(part for part in text.split(",") if part)


def _resolve_platform(args: argparse.Namespace, settings: config.Settings) -> str:
    platform = args.platform or settings.values["platform"]
    if platform == "auto":
        raise ValueError('pass --platform; the scripts cannot detect the platform when platform = "auto"')
    return platform


def _measure_claude_code(args: argparse.Namespace, settings: config.Settings) -> Measurement | None:
    claude_dir = Path(os.environ.get(ENV_CLAUDE_DIR) or Path.home() / ".claude")
    session = args.session_id or os.environ.get(ENV_SESSION) or None
    files = transcript_files(
        claude_dir, session, Path.cwd(), agents=_ids(args.agents), exclude_agents=_ids(args.exclude_agents) or frozenset()
    )
    if not files:
        return None
    usage = sum_usage(files, args.since)
    cost, unpriced = price_usage(usage, settings.values.get("prices", {}))
    return Measurement(
        "measured",
        sum(u.input for u in usage.values()), sum(u.output for u in usage.values()),
        sum(u.cache_write + u.cache_read for u in usage.values()),
        cost, sorted(usage), unpriced,
    )


def _measure_reported(args: argparse.Namespace) -> Measurement | None:
    given = (args.input_tokens, args.output_tokens, args.cache_tokens, args.cost_usd)
    if all(value is None for value in given):
        return None
    return Measurement(
        "measured", args.input_tokens, args.output_tokens, args.cache_tokens, args.cost_usd, None, [],
    )


def _measure(args: argparse.Namespace, platform: str, settings: config.Settings) -> Measurement:
    found = _measure_claude_code(args, settings) if platform == "claude-code" else None
    return found or (_measure_reported(args) if hasattr(args, "input_tokens") else None) or Measurement("unknown")


def _number(value: int | float | None) -> str:
    return "unknown" if value is None else str(value)


def _build_row(args: argparse.Namespace, platform: str, measured: Measurement) -> dict[str, str]:
    models = ",".join(measured.models) if measured.models else (args.models or "")
    return {
        "task_id": args.task_id, "date": date.today().isoformat(), "platform": platform,
        "playbook": args.playbook, "domain": args.domain, "difficulty": args.difficulty,
        "subagents": args.subagents, "models": models,
        "input_tokens": _number(measured.input), "output_tokens": _number(measured.output),
        "cache_tokens": _number(measured.cache),
        "cost_usd": "unknown" if measured.cost is None else f"{measured.cost:.4f}",
        "outcome": args.outcome, "verified": args.verified, "measurement": measured.measurement,
    }


def _cmd_suggest(args: argparse.Namespace, settings: config.Settings) -> dict:
    platform = _resolve_platform(args, settings)
    defaults = settings.values["budget"]["default_per_task"]
    suggestion = suggest_budget(_read_ledger(args.skill_dir), platform, args.playbook, args.difficulty, defaults)
    return {"budget_usd": suggestion.budget_usd, "method": suggestion.method, "n": suggestion.n}


def _cmd_usage(args: argparse.Namespace, settings: config.Settings) -> dict:
    platform = _resolve_platform(args, settings)
    measured = (_measure_claude_code(args, settings) if platform == "claude-code" else None) or Measurement("unknown")
    cost = None if measured.cost is None else round(measured.cost, 4)
    limit = over = None
    if cost is not None and args.budget is not None:
        limit = round(args.budget * settings.values["budget"]["overrun_factor"], 4)
        over = cost > limit
    return {
        "measurement": measured.measurement, "cost_usd": cost, "unpriced_models": measured.unpriced or [],
        "input_tokens": measured.input, "output_tokens": measured.output, "cache_tokens": measured.cache,
        "models": measured.models or [], "budget_usd": args.budget, "limit_usd": limit, "over_budget": over,
    }


def _cmd_record(args: argparse.Namespace, settings: config.Settings) -> dict:
    platform = _resolve_platform(args, settings)
    measured = _measure(args, platform, settings)
    result = record(args.skill_dir, _build_row(args, platform, measured))
    return {**result, "unpriced_models": measured.unpriced or []}


def _cmd_correct(args: argparse.Namespace, settings: config.Settings) -> dict:
    return correct(args.skill_dir, args.task_id, date.today())


def _since(text: str) -> datetime:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO date and time: {text!r}") from None


def _non_negative(kind: type):
    def parse(text: str):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not (value >= 0 and math.isfinite(value)):
            raise argparse.ArgumentTypeError(f"must be 0 or more: {text!r}")
        return value
    return parse


def _add_platform(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform", choices=CONCRETE_PLATFORMS, help="default: the platform setting, unless it is auto")


def _add_measuring(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since", required=True, type=_since, help="ISO start time of the task; earlier usage is ignored")
    parser.add_argument("--session-id", help=f"Claude Code session (default: ${ENV_SESSION}, else the newest in this folder)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--agents", help="comma-separated subagent ids: measure only these, not the main transcript")
    group.add_argument("--exclude-agents", help="comma-separated subagent ids to leave out")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finance.py", description="Measure task costs, suggest budgets, keep the ledger.")
    parser.add_argument(
        "--skill-dir", type=Path, default=config.DEFAULT_SKILL_DIR, help="skill folder (default: the folder above scripts/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    suggest = sub.add_parser("suggest", help="suggest a budget in equivalent USD")
    _add_platform(suggest)
    suggest.add_argument("--playbook", required=True, choices=config.PLAYBOOKS)
    suggest.add_argument("--difficulty", required=True, type=int, choices=range(1, 6))

    usage = sub.add_parser("usage", help="measure the cost since a start time")
    _add_platform(usage)
    _add_measuring(usage)
    usage.add_argument("--budget", type=_non_negative(float), help="the task budget in USD, to flag an overrun")

    rec = sub.add_parser("record", help="append a task row to the ledger")
    _add_platform(rec)
    _add_measuring(rec)
    rec.add_argument("--task-id", required=True)
    rec.add_argument("--playbook", required=True, choices=config.PLAYBOOKS)
    rec.add_argument("--domain", required=True)
    rec.add_argument("--difficulty", required=True)
    rec.add_argument("--subagents", required=True)
    rec.add_argument("--outcome", required=True)
    rec.add_argument("--verified", required=True, help="confirmed/checked claims, such as 3/3")
    rec.add_argument("--input-tokens", type=_non_negative(int))
    rec.add_argument("--output-tokens", type=_non_negative(int))
    rec.add_argument("--cache-tokens", type=_non_negative(int))
    rec.add_argument("--cost-usd", type=_non_negative(float))
    rec.add_argument("--models", help="comma-separated model names or tiers, for a row that has no measured models")

    fix = sub.add_parser("correct", help="mark a recorded task as wrong, so budgets leave it out")
    fix.add_argument("--task-id", required=True)
    return parser


_COMMANDS = {"suggest": _cmd_suggest, "usage": _cmd_usage, "record": _cmd_record, "correct": _cmd_correct}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = config.load_settings(args.skill_dir)
        result = _COMMANDS[args.command](args, settings)
    except (config.ConfigError, ValueError, OSError) as error:  # LedgerError is a ValueError
        print(f"finance.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
