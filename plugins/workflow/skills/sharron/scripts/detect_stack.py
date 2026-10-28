#!/usr/bin/env python3
"""Detect the tags of a workspace and pick the service-list skills that fit a unit of work.

Usage (from the skill folder; every subcommand prints one JSON object):
    sh scripts/run.sh detect_stack.py tags [--workspace DIR]
    sh scripts/run.sh detect_stack.py select --role R --playbook PB --domain D --tier T
                                             [--tags a,b] [--workspace DIR]

`tags` scans the workspace (default: the current folder) and prints {"tags": [...]}.
`select` unions those tags with --tags, reads registry.toml and prints
{"tags": [...], "skills": [{"name", "repo", "plugin", "matched", "min_tier"}], "dropped": [names]}.
A skill with tags is selected only when every one of its tags is among the task's tags; at most
`max_skills_per_brief` skills are kept, the most specific first, and the rest are listed as dropped.
The vocabulary is documented in references/tags.md. Bad input prints one line on stderr and exits 1.
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f"sharron scripts need Python 3.11 or newer (found {sys.version_info.major}.{sys.version_info.minor})")

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import tomllib  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import config  # noqa: E402

STACK_TAGS = (
    "python", "javascript", "typescript", "rust", "go", "terraform", "helm", "kubernetes",
    "bash", "docker", "frontend", "threejs", "cloudflare",
)
LAYER_TAGS = ("backend", "frontend", "infra", "cli", "ui-design")
ACTIVITY_TAGS = (
    "testing", "async", "concurrency", "database", "grpc", "cli", "observability", "performance",
    "new-project", "refactoring", "import", "lint",
)
VOCABULARY = frozenset(STACK_TAGS) | frozenset(LAYER_TAGS) | frozenset(ACTIVITY_TAGS)

SCHEMA_VERSION = 1
REGISTRY_FILE = "registry.toml"
ANY = "*"
SELF_REF = "self"

MAX_DEPTH = 3  # folders below the workspace that are scanned
SKIPPED_FOLDERS = frozenset({"node_modules", "venv", "dist", "build", "target", "vendor", "__pycache__"})
READ_LIMIT = 64 * 1024
SHEBANG_LIMIT = 256

_PYTHON_FILES = frozenset({"pyproject.toml", "setup.py", "requirements.txt"})
_WRANGLER_FILES = frozenset({"wrangler.toml", "wrangler.json", "wrangler.jsonc"})
_FRONTEND_PACKAGES = frozenset({"react", "react-dom", "vue", "next", "nuxt"})
_SHEBANG_RE = re.compile(rb"#!.*\b(ba)?sh\b")
_API_VERSION_RE = re.compile(r"^apiVersion:", re.MULTILINE)
_KIND_RE = re.compile(r"^kind:", re.MULTILINE)

_KEBAB_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_STATUSES = ("active", "disabled")
_INSTALL_PLATFORMS = tuple(p for p in config.PLATFORMS if p != "auto")


class RegistryError(ValueError):
    """registry.toml cannot be used; the message names the entry, the field and the offending value."""


@dataclass(frozen=True)
class Entry:
    name: str
    repo: str
    plugin: str | None
    status: str
    roles: tuple[str, ...]
    playbooks: tuple[str, ...]
    domains: tuple[str, ...]
    tags: tuple[str, ...]
    min_tier: str
    ref: str
    install: dict[str, str]


@dataclass(frozen=True)
class Tool:
    name: str
    check: str
    install: str
    run: str
    sends_data: bool


@dataclass(frozen=True)
class Registry:
    skills: tuple[Entry, ...]
    tools: tuple[Tool, ...]


# ---------------------------------------------------------------- detection


def _read_head(path: Path, limit: int = READ_LIMIT) -> bytes:
    """The first `limit` bytes of a regular file; empty when it cannot be read."""
    try:
        if not path.is_file():  # also keeps a pipe or a device from blocking the scan
            return b""
        with path.open("rb") as handle:
            return handle.read(limit)
    except OSError:
        return b""


def _package_tags(path: Path) -> set[str]:
    tags = {"javascript"}
    try:
        manifest = json.loads(_read_head(path).decode("utf-8", errors="replace"))
    except ValueError:
        return tags
    if not isinstance(manifest, dict):
        return tags
    deps: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        if isinstance(manifest.get(section), dict):
            deps.update(manifest[section])
    if deps & _FRONTEND_PACKAGES:
        tags.add("frontend")
    if "three" in deps:
        tags.add("threejs")
    return tags


def _file_tags(path: Path) -> set[str]:
    name = path.name
    suffix = path.suffix
    tags: set[str] = set()
    if name in _PYTHON_FILES:
        tags.add("python")
    if name == "package.json":
        tags |= _package_tags(path)
    if name == "tsconfig.json":
        tags.add("typescript")
    if name == "Cargo.toml":
        tags.add("rust")
    if name == "go.mod":
        tags.add("go")
    if suffix == ".tf":
        tags.add("terraform")
    if name == "Chart.yaml":
        tags |= {"helm", "kubernetes"}
    if suffix in (".yaml", ".yml"):
        text = _read_head(path).decode("utf-8", errors="replace")
        if _API_VERSION_RE.search(text) and _KIND_RE.search(text):
            tags.add("kubernetes")
    if suffix in (".sh", ".bash") or _SHEBANG_RE.match(_read_head(path, SHEBANG_LIMIT).split(b"\n", 1)[0]):
        tags.add("bash")
    if name == "Dockerfile":
        tags.add("docker")
    if name in _WRANGLER_FILES:
        tags.add("cloudflare")
    return tags


def detect_tags(workspace: Path) -> set[str]:
    """Stack tags of the files in the workspace and in the folders up to MAX_DEPTH levels below it."""
    root = Path(workspace)
    tags: set[str] = set()
    for folder, subfolders, files in os.walk(root):
        depth = len(Path(folder).relative_to(root).parts)
        if depth >= MAX_DEPTH:
            subfolders[:] = []
        else:
            subfolders[:] = [d for d in subfolders if not d.startswith(".") and d not in SKIPPED_FOLDERS]
        for file in files:
            tags |= _file_tags(Path(folder) / file)
    return tags


# ---------------------------------------------------------------- registry


def _fail(label: str, field: str, value: Any, problem: str) -> RegistryError:
    return RegistryError(f"{REGISTRY_FILE}: {label}: {field} {value!r} {problem}")


def _text(table: dict, label: str, field: str, *, required: bool = True, empty: bool = False) -> str | None:
    if field not in table:
        if required:
            raise RegistryError(f"{REGISTRY_FILE}: {label}: {field} is missing")
        return None
    value = table[field]
    if not isinstance(value, str):
        raise _fail(label, field, value, "must be a string")
    if not value and not empty:
        raise _fail(label, field, value, "must not be empty")
    return value


def _choice(value: str, label: str, field: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise _fail(label, field, value, "is not one of: " + ", ".join(allowed))
    return value


def _strings(table: dict, label: str, field: str) -> tuple[str, ...]:
    if field not in table:
        raise RegistryError(f"{REGISTRY_FILE}: {label}: {field} is missing")
    values = table[field]
    if not isinstance(values, list):
        raise _fail(label, field, values, "must be a list of strings")
    for value in values:
        if not isinstance(value, str):
            raise _fail(label, field, value, "must be a string")
    return tuple(values)


def _subset(values: tuple[str, ...], label: str, field: str, allowed: tuple[str, ...] | frozenset[str]) -> tuple[str, ...]:
    for value in values:
        if value not in allowed:
            raise _fail(label, field, value, "is not allowed; use " + ", ".join(sorted(allowed)))
    return values


def _entry(raw: Any, position: int) -> Entry:
    if not isinstance(raw, dict):
        raise RegistryError(f"{REGISTRY_FILE}: skills entry {position}: {raw!r} must be a table")
    name = _text(raw, f"skills entry {position}", "name")
    if not _KEBAB_RE.fullmatch(name) or len(name) > 64:
        raise _fail(f"skills entry {position}", "name", name, "must be kebab-case, at most 64 characters")
    label = f"skill {name!r}"
    repo = _text(raw, label, "repo")
    if not _REPO_RE.fullmatch(repo):
        raise _fail(label, "repo", repo, "must look like owner/name")
    plugin = _text(raw, label, "plugin", required=False)
    status = _choice(_text(raw, label, "status"), label, "status", _STATUSES)
    roles = _subset(_strings(raw, label, "roles"), label, "roles", {*config.ROLES, ANY})
    playbooks = _subset(_strings(raw, label, "playbooks"), label, "playbooks", {*config.PLAYBOOKS, ANY})
    domains = _strings(raw, label, "domains")
    for domain in domains:
        if domain != ANY and not _KEBAB_RE.fullmatch(domain):
            raise _fail(label, "domains", domain, "must be kebab-case or *")
    tags = _subset(_strings(raw, label, "tags"), label, "tags", VOCABULARY)
    min_tier = _choice(_text(raw, label, "min_tier"), label, "min_tier", config.TIERS)
    ref = _text(raw, label, "ref")
    if ref != SELF_REF and not _SHA_RE.fullmatch(ref):
        raise _fail(label, "ref", ref, f"must be 40 lowercase hex characters or {SELF_REF!r}")
    return Entry(name, repo, plugin, status, roles, playbooks, domains, tags, min_tier, ref, _install(raw, label))


def _install(raw: dict, label: str) -> dict[str, str]:
    install = raw.get("install", {})
    if not isinstance(install, dict):
        raise _fail(label, "install", install, "must be a table")
    for platform, command in install.items():
        if platform not in _INSTALL_PLATFORMS:
            raise _fail(label, "install", platform, "is not a platform; use " + ", ".join(_INSTALL_PLATFORMS))
        if not isinstance(command, str) or not command.strip():
            raise _fail(label, f"install.{platform}", command, "must be a non-empty string")
    return dict(install)


def _tool(raw: Any, position: int) -> Tool:
    label = f"tools entry {position}"
    if not isinstance(raw, dict):
        raise RegistryError(f"{REGISTRY_FILE}: {label}: {raw!r} must be a table")
    name = _text(raw, label, "name")
    label = f"tool {name!r}"
    check = _text(raw, label, "check")
    install = _text(raw, label, "install", empty=True)
    run = _text(raw, label, "run")
    sends_data = raw.get("sends_data")
    if not isinstance(sends_data, bool):
        raise _fail(label, "sends_data", sends_data, "must be true or false")
    return Tool(name, check, install, run, sends_data)


def _table_list(raw: dict, key: str) -> list:
    items = raw.get(key, [])
    if not isinstance(items, list):
        raise RegistryError(f"{REGISTRY_FILE}: {key} {items!r} must be an array of tables")
    return items


def load_registry(path: Path) -> Registry:
    try:
        with Path(path).open("rb") as handle:
            raw = tomllib.load(handle)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise RegistryError(f"{REGISTRY_FILE}: {e}") from e
    version = raw.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise RegistryError(f"{REGISTRY_FILE}: schema_version {version!r} is not supported; use {SCHEMA_VERSION}")
    skills = tuple(_entry(item, i) for i, item in enumerate(_table_list(raw, "skills"), 1))
    tools = tuple(_tool(item, i) for i, item in enumerate(_table_list(raw, "tools"), 1))
    return Registry(skills, tools)


# ---------------------------------------------------------------- selection


def select_skills(
    registry: Registry, *, role: str, playbook: str, domain: str, tier: str, tags: set[str], limit: int
) -> tuple[list[Entry], list[Entry]]:
    """Return (selected, dropped): the fitting entries, most specific first, split at `limit`."""
    rank = config.TIERS.index(tier)
    fitting = [
        entry
        for entry in registry.skills
        if entry.status == "active"
        and (ANY in entry.roles or role in entry.roles)
        and (ANY in entry.playbooks or playbook in entry.playbooks)
        and (ANY in entry.domains or domain in entry.domains)
        and config.TIERS.index(entry.min_tier) <= rank
        and set(entry.tags) <= tags
    ]
    # sorted() is stable, so entries that tie keep their registry order.
    ordered = sorted(fitting, key=lambda entry: (-len(entry.tags), config.TIERS.index(entry.min_tier)))
    return ordered[:limit], ordered[limit:]


# ---------------------------------------------------------------- command line


def _split_tags(text: str) -> set[str]:
    wanted = {part.strip() for part in text.split(",") if part.strip()}
    unknown = sorted(wanted - VOCABULARY)
    if unknown:
        raise ValueError(f"unknown tag {', '.join(unknown)}; the tags are listed in references/tags.md")
    return wanted


def _workspace_tags(workspace: Path) -> set[str]:
    if not workspace.is_dir():
        raise ValueError(f"workspace {str(workspace)!r} is not a folder")
    return detect_tags(workspace)


def _cmd_tags(args: argparse.Namespace) -> dict:
    return {"tags": sorted(_workspace_tags(args.workspace))}


def _cmd_select(args: argparse.Namespace) -> dict:
    extra = _split_tags(args.tags)
    tags = _workspace_tags(args.workspace) | extra
    limit = config.load_settings(args.skill_dir).values["max_skills_per_brief"]
    registry = load_registry(args.skill_dir / REGISTRY_FILE)
    selected, dropped = select_skills(
        registry, role=args.role, playbook=args.playbook, domain=args.domain, tier=args.tier, tags=tags, limit=limit
    )
    return {
        "tags": sorted(tags),
        "skills": [
            {"name": e.name, "repo": e.repo, "plugin": e.plugin, "matched": list(e.tags), "min_tier": e.min_tier}
            for e in selected
        ],
        "dropped": [e.name for e in dropped],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="detect_stack.py", description="Detect workspace tags and select skills.")
    parser.add_argument(
        "--skill-dir", type=Path, default=config.DEFAULT_SKILL_DIR, help="skill folder (default: the folder above scripts/)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    found = sub.add_parser("tags", help="print the tags detected in a workspace")
    found.add_argument("--workspace", type=Path, default=Path("."), help="folder to scan (default: the current folder)")

    pick = sub.add_parser("select", help="pick the service-list skills for a unit of work")
    pick.add_argument("--role", required=True, choices=config.ROLES)
    pick.add_argument("--playbook", required=True, choices=config.PLAYBOOKS)
    pick.add_argument("--domain", required=True)
    pick.add_argument("--tier", required=True, choices=config.TIERS)
    pick.add_argument("--tags", default="", help="comma-separated tags to add to the detected ones")
    pick.add_argument("--workspace", type=Path, default=Path("."), help="folder to scan (default: the current folder)")
    return parser


_COMMANDS = {"tags": _cmd_tags, "select": _cmd_select}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _COMMANDS[args.command](args)
    except (config.ConfigError, ValueError, OSError) as error:  # RegistryError is a ValueError
        print(f"detect_stack.py: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
