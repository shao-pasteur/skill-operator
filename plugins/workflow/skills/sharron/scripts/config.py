#!/usr/bin/env python3
"""Show or validate the effective settings of the sharron skill.

Usage (from the skill folder):
    sh scripts/run.sh config.py show        one line per setting: its value and where it came from
    sh scripts/run.sh config.py validate    check config.toml and SHARRON_PLATFORM; exit 1 on errors

The defaults are in config.example.toml. config.toml (gitignored, next to it) holds only the keys the
user changed and is merged over the defaults; the SHARRON_PLATFORM environment variable overrides
`platform`. Unlike the other scripts it prints text lines, and it prints its errors on stdout too.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import tomllib  # noqa: E402
from collections.abc import Callable, Iterator, Mapping  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

# Shared vocabularies: every other script imports them from here.
PLATFORMS = ("auto", "claude-code", "codex", "copilot", "cursor", "work", "hybrid")
ROLES = (
    "sharron", "planner", "researcher", "verifier", "reviewer", "security", "analyst",
    "writer", "engineer", "diagnostician", "operator", "tutor", "finance",
)
TIERS = ("T1", "T2", "T3")
PLAYBOOKS = (
    "simple-answer", "research", "planning", "action", "decision-support",
    "learning", "coding", "settings-help", "custom", "maintenance",
)
# Task ids such as t-20261027-01 become file names, so the digits must be ASCII.
TASK_ID_RE = re.compile(r"^[a-z]+-\d{8}-\d{2,}$", re.ASCII)

EXAMPLE_FILE = "config.example.toml"
CONFIG_FILE = "config.toml"
ENV_PLATFORM = "SHARRON_PLATFORM"
PRICE_FIELDS = ("input", "output", "cache_write", "cache_read")
DEFAULT_SKILL_DIR = Path(__file__).resolve().parent.parent
_BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_CURRENCY_RE = re.compile(r"[A-Z]{3}")


class ConfigError(Exception):
    """A settings file cannot be read; the message starts with the file name."""


@dataclass(frozen=True)
class Problem:
    level: str  # "error" or "warning"
    key: str  # dotted path, for example roles.reviewer
    message: str


@dataclass(frozen=True)
class Settings:
    values: dict
    # Dotted key of every leaf (a list is a leaf) -> "default", "config.toml" or "SHARRON_PLATFORM".
    # In display order: the example's keys in its order, then the keys only config.toml has.
    sources: dict[str, str]


# ---------------------------------------------------------------- loading


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path.name}: {e}") from e


def _read_files(skill_dir: Path) -> tuple[dict, dict]:
    """Return the example's defaults and the user's config.toml (empty when there is none)."""
    defaults = _read_toml(skill_dir / EXAMPLE_FILE)
    user_path = skill_dir / CONFIG_FILE
    user = _read_toml(user_path) if user_path.exists() else {}
    return defaults, user


def _merge(defaults: dict, user: dict) -> dict:
    """Merge the user's tables into the defaults key by key; any other user value replaces the default."""
    merged = dict(defaults)
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _leaves(table: dict, prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Yield (key path, value) for every setting that is not a table, in table order."""
    for key, value in table.items():
        if isinstance(value, dict):
            yield from _leaves(value, (*prefix, key))
        else:
            yield (*prefix, key), value


def _dotted(path: tuple[str, ...]) -> str:
    """Join a key path with dots; a part that is not a bare TOML key is quoted, as in prices."gpt-5.1".input."""
    return ".".join(
        part if _BARE_KEY_RE.fullmatch(part) else json.dumps(part, ensure_ascii=False) for part in path
    )


def load_settings(skill_dir: Path, environ: Mapping[str, str] = os.environ) -> Settings:
    defaults, user = _read_files(skill_dir)
    values = _merge(defaults, user)
    platform = environ.get(ENV_PLATFORM)
    if platform:
        values["platform"] = platform
    from_user = {path for path, _ in _leaves(user)}

    def source(path: tuple[str, ...]) -> str:
        if path == ("platform",) and platform:
            return ENV_PLATFORM
        return CONFIG_FILE if path in from_user else "default"

    in_example = [path for path, _ in _leaves(defaults)]
    in_values = [path for path, _ in _leaves(values)]
    example_keys, value_keys = set(in_example), set(in_values)
    ordered = [path for path in in_example if path in value_keys]
    ordered += [path for path in in_values if path not in example_keys]
    return Settings(values, {_dotted(path): source(path) for path in ordered})


# ---------------------------------------------------------------- validation


@dataclass(frozen=True)
class _Rule:
    """A check for one value; `use` completes the message "<value> is not allowed; use <use>"."""

    ok: Callable[[Any], bool]
    use: str


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return _is_int(value) or (isinstance(value, float) and math.isfinite(value))


_PLATFORM = _Rule(lambda v: isinstance(v, str) and v in PLATFORMS, "one of: " + ", ".join(PLATFORMS))
_TIER = _Rule(lambda v: isinstance(v, str) and v in TIERS, "one of: " + ", ".join(TIERS))
_FLAG = _Rule(lambda v: isinstance(v, bool), "true or false")
_COUNT = _Rule(lambda v: _is_int(v) and 1 <= v <= 10, "a whole number from 1 to 10")
_CURRENCY = _Rule(
    lambda v: isinstance(v, str) and _CURRENCY_RE.fullmatch(v) is not None, "three capital letters, such as TWD"
)
_AMOUNT = _Rule(lambda v: _is_number(v) and v >= 0, "a number ≥ 0")
_POSITIVE = _Rule(lambda v: _is_number(v) and v > 0, "a number > 0")
_FACTOR = _Rule(lambda v: _is_number(v) and v > 1, "a number > 1")
_TEXT = _Rule(lambda v: isinstance(v, str), "a string in quotes")
_TEXTS = _Rule(
    lambda v: isinstance(v, list) and all(isinstance(item, str) for item in v), "a list of strings in quotes"
)

_ANY = "*"  # in a schema table, the entry for every key that is not named


def _platform_table(platform: str) -> dict:
    table: dict = {"models": {tier: _TEXT for tier in TIERS}}
    if platform == "hybrid":
        table["available"] = _TEXTS
    return table


# A schema is a _Rule for one value, or a dict of key -> schema for a table. Keys it does not name are unknown.
_SCHEMA = {
    "platform": _PLATFORM,
    "auto_install": _FLAG,
    "max_parallel_subagents": _COUNT,
    "max_skills_per_brief": _COUNT,
    "platforms": {platform: _platform_table(platform) for platform in PLATFORMS if platform != "auto"},
    "roles": {role: _TIER for role in ROLES},
    "prices": {_ANY: {field: _AMOUNT for field in PRICE_FIELDS}},
    "risk": {"currency": _CURRENCY, "small_amount": _AMOUNT, "large_amount": _AMOUNT},
    "budget": {"default_per_task": {str(n): _POSITIVE for n in range(1, 6)}, "overrun_factor": _FACTOR},
    "standing_orders": {"always": _TEXTS, "never": _TEXTS},
    "installed": {_ANY: {field: _TEXT for field in ("source", "version", "date", "platform")}},
}


def _show(value: Any) -> str:
    """Render a value for messages and `show`: JSON, except that a TOML date or time stays unquoted."""
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    return json.dumps(value, ensure_ascii=False, default=str)


def _bad(path: tuple[str, ...], value: Any, use: str) -> Problem:
    return Problem("error", _dotted(path), f"{_show(value)} is not allowed; use {use}")


def _walk(path: tuple[str, ...], value: Any, schema: Any, problems: list[Problem]) -> None:
    if isinstance(schema, _Rule):
        if not schema.ok(value):
            problems.append(_bad(path, value, schema.use))
        return
    if not isinstance(value, dict):
        problems.append(_bad(path, value, "a table"))
        return
    for key, item in value.items():
        child = schema.get(key, schema.get(_ANY))
        if child is None:
            problems.append(Problem("warning", _dotted((*path, key)), "unknown setting; it has no effect"))
        else:
            _walk((*path, key), item, child, problems)


def _cross_checks(values: dict, problems: list[Problem]) -> None:
    """Rules that compare settings with each other, or ask for keys that must be present."""
    risk = values.get("risk")
    if isinstance(risk, dict):
        small, large = risk.get("small_amount"), risk.get("large_amount")
        if _AMOUNT.ok(small) and _AMOUNT.ok(large) and small >= large:
            message = f"must be greater than risk.small_amount ({_show(small)})"
            problems.append(Problem("error", "risk.large_amount", message))
    prices = values.get("prices")
    if isinstance(prices, dict):
        for model, entry in prices.items():
            if isinstance(entry, dict):
                for field in PRICE_FIELDS:
                    if field not in entry:
                        key = _dotted(("prices", model, field))
                        problems.append(Problem("error", key, "is required; use a number ≥ 0"))


def validate_settings(skill_dir: Path, environ: Mapping[str, str] = os.environ) -> list[Problem]:
    """Check the example merged with config.toml, then the environment, so each problem names where it is."""
    defaults, user = _read_files(skill_dir)
    values = _merge(defaults, user)
    problems: list[Problem] = []
    _walk((), values, _SCHEMA, problems)
    _cross_checks(values, problems)
    platform = environ.get(ENV_PLATFORM)
    if platform and not _PLATFORM.ok(platform):
        message = f"{_show(platform)} (from {ENV_PLATFORM}) is not allowed; use {_PLATFORM.use}"
        problems.append(Problem("error", "platform", message))
    return problems


# ---------------------------------------------------------------- command line


def _cmd_show(skill_dir: Path) -> int:
    settings = load_settings(skill_dir)
    values = {_dotted(path): value for path, value in _leaves(settings.values)}
    for key, source in settings.sources.items():
        print(f"{key} = {_show(values[key])}  # {source}")
    return 0


def _cmd_validate(skill_dir: Path) -> int:
    problems = validate_settings(skill_dir)
    for problem in problems:
        print(f"{'ERROR' if problem.level == 'error' else 'WARN'} {problem.key}: {problem.message}")
    errors = sum(problem.level == "error" for problem in problems)
    print(f"{errors} error(s), {len(problems) - errors} warning(s)")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="config.py", description="Show or validate the sharron settings.")
    parser.add_argument(
        "--skill-dir", type=Path, default=DEFAULT_SKILL_DIR, help="skill folder (default: the folder above scripts/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print every effective setting with where its value came from")
    sub.add_parser("validate", help="check config.toml and SHARRON_PLATFORM; exit 1 when there is an error")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _cmd_show(args.skill_dir) if args.command == "show" else _cmd_validate(args.skill_dir)
    except ConfigError as e:
        print(f"ERROR {e}")
        return 1


if __name__ == "__main__":
    # The messages contain "≥" and standing orders may be Chinese, so do not depend on the console's code page.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
