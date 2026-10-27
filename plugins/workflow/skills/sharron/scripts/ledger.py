"""The cost ledger format of the sharron skill: parse, validate, render and merge ledger/costs.md.

This module is imported by finance.py and datasync.py; it is not run directly. The ledger file is
generated: render_ledger writes the whole file, including the summary block, in one canonical layout,
so parse_ledger(text) followed by render_ledger gives back the same text.
"""

import datetime
import re
import statistics
from dataclasses import dataclass

import config

TASK_COLUMNS = (
    "task_id", "date", "platform", "playbook", "domain", "difficulty", "subagents", "models",
    "input_tokens", "output_tokens", "cache_tokens", "cost_usd", "outcome", "verified", "measurement",
)
CORRECTION_COLUMNS = ("task_id", "date")
SUMMARY_COLUMNS = ("platform", "playbook", "difficulty", "n", "median_usd", "p80_usd")
OUTCOMES = ("done", "partial", "failed", "cancelled")
SUMMARY_START = "<!-- summary:start -->"
SUMMARY_END = "<!-- summary:end -->"

TITLE = "# sharron cost ledger"
NOTE = "Written by `scripts/finance.py`; rows are append-only. Do not edit by hand."
SUMMARY_HEADING = "## Summary"
SUMMARY_NOTE = "Successful measured tasks (outcome done, every checked claim confirmed, no correction), in equivalent USD."
TASKS_HEADING = "## Tasks"
CORRECTIONS_HEADING = "## Corrections"

# fullmatch is used everywhere: a "$" anchor would accept a trailing newline, which breaks a table row.
_DOMAIN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_INT_RE = re.compile(r"[0-9]+")
_COUNT_RE = re.compile(r"[0-9]+|unknown")
_COST_RE = re.compile(r"[0-9]+\.[0-9]{4}|unknown")
_VERIFIED_RE = re.compile(r"([0-9]+)/([0-9]+)")
_MODEL_RE = re.compile(r"[A-Za-z0-9._:@\[\]-]+")


class LedgerError(ValueError):
    """The ledger text or a row is not in the ledger format."""


@dataclass
class Ledger:
    tasks: list[dict[str, str]]
    corrections: list[dict[str, str]]


def p80(values: list[float]) -> float:
    """The 80th percentile (inclusive method); the single value when there is only one."""
    if not values:
        raise ValueError("p80 needs at least one value")
    if len(values) == 1:
        return values[0]  # statistics.quantiles raises on one value before Python 3.13
    return statistics.quantiles(values, n=5, method="inclusive")[3]


def _check_date(field: str, value: str) -> None:
    if not _DATE_RE.fullmatch(value):
        raise LedgerError(f"{field} must be YYYY-MM-DD, got {value!r}")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise LedgerError(f"{field} is not a real date: {value!r}") from None


def _check_task_id(value: str) -> None:
    if not config.TASK_ID_RE.fullmatch(value):
        raise LedgerError(f"task_id must look like t-20261027-01, got {value!r}")


def _check_keys(row: dict[str, str], columns: tuple[str, ...]) -> None:
    if not isinstance(row, dict) or set(row) != set(columns):
        raise LedgerError(f"a row needs exactly these fields: {', '.join(columns)}")
    for key, value in row.items():
        if not isinstance(value, str):
            raise LedgerError(f"{key} must be a string, got {value!r}")


def validate_task_row(row: dict[str, str]) -> None:
    """Raise LedgerError unless every field of a task row follows the ledger rules."""
    _check_keys(row, TASK_COLUMNS)
    _check_task_id(row["task_id"])
    _check_date("date", row["date"])
    if row["platform"] not in config.PLATFORMS or row["platform"] == "auto":
        raise LedgerError(f"platform must be a concrete platform, got {row['platform']!r}")
    if row["playbook"] not in config.PLAYBOOKS:
        raise LedgerError(f"playbook must be one of {', '.join(config.PLAYBOOKS)}, got {row['playbook']!r}")
    if not _DOMAIN_RE.fullmatch(row["domain"]):
        raise LedgerError(f"domain must be lowercase words joined by hyphens, got {row['domain']!r}")
    if row["difficulty"] not in ("1", "2", "3", "4", "5"):
        raise LedgerError(f"difficulty must be 1 to 5, got {row['difficulty']!r}")
    if not _INT_RE.fullmatch(row["subagents"]):
        raise LedgerError(f"subagents must be a whole number, got {row['subagents']!r}")
    models = row["models"]
    if models and not all(_MODEL_RE.fullmatch(m) for m in models.split(",")):
        raise LedgerError(f"models must be comma-separated model names, got {models!r}")
    for key in ("input_tokens", "output_tokens", "cache_tokens"):
        if not _COUNT_RE.fullmatch(row[key]):
            raise LedgerError(f"{key} must be a whole number or unknown, got {row[key]!r}")
    if not _COST_RE.fullmatch(row["cost_usd"]):
        raise LedgerError(f"cost_usd must have 4 decimals or be unknown, got {row['cost_usd']!r}")
    if row["outcome"] not in OUTCOMES:
        raise LedgerError(f"outcome must be one of {', '.join(OUTCOMES)}, got {row['outcome']!r}")
    verified = _VERIFIED_RE.fullmatch(row["verified"])
    if not verified or int(verified[1]) > int(verified[2]):
        raise LedgerError(f"verified must be confirmed/checked with confirmed <= checked, got {row['verified']!r}")
    if row["measurement"] not in ("measured", "unknown"):
        raise LedgerError(f"measurement must be measured or unknown, got {row['measurement']!r}")


def _validate_correction(row: dict[str, str]) -> None:
    _check_keys(row, CORRECTION_COLUMNS)
    _check_task_id(row["task_id"])
    _check_date("date", row["date"])


def successful_rows(ledger: Ledger) -> list[dict[str, str]]:
    """Measured tasks that finished done, with every checked claim confirmed and no correction."""
    corrected = {c["task_id"] for c in ledger.corrections}
    rows = []
    for row in ledger.tasks:
        verified = _VERIFIED_RE.fullmatch(row["verified"])
        if (
            row["measurement"] == "measured"
            and row["cost_usd"] != "unknown"
            and row["outcome"] == "done"
            and verified
            and verified[1] == verified[2]
            and row["task_id"] not in corrected
        ):
            rows.append(row)
    return rows


def _table_line(cells: list[str] | tuple[str, ...]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(columns: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    lines = [_table_line(columns), "|" + "---|" * len(columns)]
    lines += [_table_line(cells) for cells in rows]
    return lines


def _summary_rows(ledger: Ledger) -> list[list[str]]:
    groups: dict[tuple[str, str, int], list[float]] = {}
    for row in successful_rows(ledger):
        key = (row["platform"], row["playbook"], int(row["difficulty"]))
        groups.setdefault(key, []).append(float(row["cost_usd"]))
    return [
        [platform, playbook, str(difficulty), str(len(costs)),
         f"{statistics.median(costs):.4f}", f"{p80(costs):.4f}"]
        for (platform, playbook, difficulty), costs in sorted(groups.items())
    ]


def render_ledger(ledger: Ledger) -> str:
    """Return the whole ledger file, summary block included. Raises LedgerError on an invalid row."""
    for task in ledger.tasks:
        validate_task_row(task)
    for correction in ledger.corrections:
        _validate_correction(correction)
    lines = [TITLE, "", NOTE, "", SUMMARY_HEADING, "", SUMMARY_NOTE, "", SUMMARY_START]
    lines += _table(SUMMARY_COLUMNS, _summary_rows(ledger))
    lines += [SUMMARY_END, "", TASKS_HEADING, ""]
    lines += _table(TASK_COLUMNS, [[t[c] for c in TASK_COLUMNS] for t in ledger.tasks])
    lines += ["", CORRECTIONS_HEADING, ""]
    lines += _table(CORRECTION_COLUMNS, [[c[k] for k in CORRECTION_COLUMNS] for c in ledger.corrections])
    return "\n".join(lines) + "\n"


def _split_cells(line: str) -> list[str]:
    if not (line.startswith("|") and line.endswith("|") and len(line) >= 2):
        raise LedgerError(f"not a table row: {line!r}")
    return [cell.strip() for cell in line[1:-1].split("|")]


def _parse_table(lines: list[str], heading: str, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if lines.count(heading) != 1:
        raise LedgerError(f"the ledger needs exactly one {heading!r} section")
    rest = lines[lines.index(heading) + 1:]
    start = next((i for i, line in enumerate(rest) if line.strip()), len(rest))
    table = []
    for line in rest[start:]:
        if not line.startswith("|"):
            break
        table.append(line)
    if len(table) < 2:
        raise LedgerError(f"the {heading!r} section has no table")
    if tuple(_split_cells(table[0])) != columns:
        raise LedgerError(f"the {heading!r} table must have the columns {' | '.join(columns)}")
    if _split_cells(table[1]) != ["---"] * len(columns):
        raise LedgerError(f"the {heading!r} table needs a |---| separator row")
    rows = []
    for line in table[2:]:
        cells = _split_cells(line)
        if len(cells) != len(columns):
            raise LedgerError(f"a row in {heading!r} has {len(cells)} cells, expected {len(columns)}")
        rows.append(dict(zip(columns, cells)))
    return rows


def _outside_summary(text: str) -> tuple[str, str] | None:
    """The text before the summary start marker and after the end marker, or None if they are missing."""
    head, start, rest = text.partition(SUMMARY_START)
    _, end, tail = rest.partition(SUMMARY_END)
    return (head, tail) if start and end else None


def parse_ledger(text: str) -> Ledger:
    """Read a ledger file and validate every row.

    The summary block is generated and may be stale, so its content is ignored. Everything else must
    be exactly what render_ledger writes: stray lines, such as git conflict markers, raise LedgerError
    instead of silently dropping the rows after them.
    """
    text = text.replace("\r\n", "\n")
    lines = text.splitlines()
    tasks = _parse_table(lines, TASKS_HEADING, TASK_COLUMNS)
    corrections = _parse_table(lines, CORRECTIONS_HEADING, CORRECTION_COLUMNS)
    for task in tasks:
        validate_task_row(task)
    for correction in corrections:
        _validate_correction(correction)
    ledger = Ledger(tasks, corrections)
    if _outside_summary(text) != _outside_summary(render_ledger(ledger)):
        raise LedgerError("the ledger has lines or a layout that sharron did not write")
    return ledger


def merge_ledgers(upstream: str, local: str) -> str:
    """Keep every upstream row, then add the local rows that are new (by task_id, or task_id and date)."""
    up, mine = parse_ledger(upstream), parse_ledger(local)
    task_ids = {t["task_id"] for t in up.tasks}
    tasks = up.tasks + [t for t in mine.tasks if t["task_id"] not in task_ids]
    corrections: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for correction in up.corrections + mine.corrections:
        key = (correction["task_id"], correction["date"])
        if key not in seen:
            seen.add(key)
            corrections.append(correction)
    return render_ledger(Ledger(tasks, corrections))
