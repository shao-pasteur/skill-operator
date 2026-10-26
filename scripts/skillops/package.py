"""Zip each web-compatible skill for manual upload to claude.ai, ChatGPT and Gemini."""

import zipfile
from pathlib import Path

from skillops.catalog import Catalog

EXCLUDE_NAMES = frozenset({"__pycache__", ".DS_Store", ".git"})
EXCLUDE_SUFFIXES = (".pyc",)
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _included_files(skill_path: Path) -> list[Path]:
    files = []
    for path in skill_path.rglob("*"):
        rel_parts = path.relative_to(skill_path).parts
        if not path.is_file() or any(part in EXCLUDE_NAMES for part in rel_parts):
            continue
        if path.name.endswith(EXCLUDE_SUFFIXES):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(skill_path).as_posix())


def package_skills(catalog: Catalog, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.zip"):
        old.unlink()
    written = []
    for skill in sorted((s for s in catalog.skills if s.web), key=lambda s: s.name):
        target = out_dir / f"{skill.name}.zip"
        with zipfile.ZipFile(target, "w") as zf:
            for path in _included_files(skill.path):
                info = zipfile.ZipInfo(f"{skill.name}/{path.relative_to(skill.path).as_posix()}", _FIXED_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                info.external_attr = mode << 16
                zf.writestr(info, path.read_bytes())
        written.append(target)
    return written
