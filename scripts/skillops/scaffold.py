"""Create a new skill from the template, or copy an existing skill folder into the repo."""

import shutil
from pathlib import Path

from skillops.catalog import NAME_RE, load_catalog
from skillops.package import EXCLUDE_NAMES, EXCLUDE_SUFFIXES

SKILL_TEMPLATE = """---
name: {name}
description: TODO 描述這個 skill 做什麼，以及什麼時候該使用它（寫進使用者可能會說的關鍵字）。
---

# {name}

TODO 撰寫指令。
"""


class ScaffoldError(Exception):
    pass


def _destination(root: Path, category: str, name: str) -> Path:
    if not NAME_RE.match(name) or len(name) > 64:
        raise ScaffoldError(f"name「{name}」格式錯誤：只能用小寫英數字與單一連字號，最多 64 字元")
    catalog = load_catalog(root)
    if category not in {c.id for c in catalog.categories}:
        raise ScaffoldError(f"分類「{category}」不在 categories.yaml 中")
    existing = next((s for s in catalog.skills if s.dir_name == name), None)
    if existing:
        raise ScaffoldError(f"skill「{name}」已存在：{existing.rel_path}")
    dest = root / "plugins" / category / "skills" / name
    if dest.exists():
        raise ScaffoldError(f"{dest.relative_to(root).as_posix()} 已存在")
    return dest


def new_skill(root: Path, category: str, name: str) -> Path:
    dest = _destination(root, category, name)
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(SKILL_TEMPLATE.format(name=name), encoding="utf-8")
    return dest


def import_skill(root: Path, src: Path, category: str) -> Path:
    src = src.expanduser().resolve()
    if not (src / "SKILL.md").is_file():
        raise ScaffoldError(f"{src} 裡沒有 SKILL.md")
    dest = _destination(root, category, src.name)
    patterns = [*EXCLUDE_NAMES, *(f"*{suffix}" for suffix in EXCLUDE_SUFFIXES)]
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*patterns))
    return dest
