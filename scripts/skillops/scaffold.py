"""Create a new skill from the template, or copy an existing skill folder into the repo."""

import shutil
from pathlib import Path

from skillops.catalog import NAME_RE, load_catalog
from skillops.package import EXCLUDE_PATTERNS

SKILL_TEMPLATE = """---
name: {name}
description: TODO Describe what this skill does and when to use it, including words users are likely to say.
---

# {name}

TODO Write the instructions.
"""


class ScaffoldError(Exception):
    pass


def _destination(root: Path, category: str, name: str) -> Path:
    if not NAME_RE.match(name) or len(name) > 64:
        raise ScaffoldError(f"name '{name}' is invalid: use lowercase letters, digits and single hyphens, at most 64 characters")
    catalog = load_catalog(root)
    if category not in {c.id for c in catalog.categories}:
        raise ScaffoldError(f"category '{category}' is not in categories.yaml")
    existing = next((s for s in catalog.skills if s.dir_name == name), None)
    if existing:
        raise ScaffoldError(f"skill '{name}' already exists: {existing.rel_path}")
    dest = root / "plugins" / category / "skills" / name
    if dest.exists():
        raise ScaffoldError(f"{dest.relative_to(root).as_posix()} already exists")
    return dest


def new_skill(root: Path, category: str, name: str) -> Path:
    dest = _destination(root, category, name)
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(SKILL_TEMPLATE.format(name=name), encoding="utf-8")
    return dest


def import_skill(root: Path, src: Path, category: str) -> Path:
    src = src.expanduser().resolve()
    if not (src / "SKILL.md").is_file():
        raise ScaffoldError(f"no SKILL.md in {src}")
    links = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_symlink())
    if links:
        # A link could pull files from outside the skill into this public repo.
        raise ScaffoldError(f"{src} contains symlinks; replace them with real files before importing: {', '.join(links)}")
    dest = _destination(root, category, src.name)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS))
    return dest
