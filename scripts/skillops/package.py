"""Zip each web-compatible skill for manual upload to claude.ai, ChatGPT and Gemini."""

import fnmatch
import zipfile
from pathlib import Path

from skillops.catalog import Catalog

# Matched against every path component; .env files must never reach a zip or the public repo.
EXCLUDE_PATTERNS = ("__pycache__", ".git", ".DS_Store", "._*", "Thumbs.db", "*.pyc", ".env", ".env.*")
# Only folders carrying this marker (i.e. created by package_skills) get their old zips cleared.
DIST_MARKER = ".skillops-dist"
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _included_files(skill_path: Path) -> list[Path]:
    files = []
    for path in skill_path.rglob("*"):
        rel_parts = path.relative_to(skill_path).parts
        if not path.is_file() or any(
            fnmatch.fnmatch(part, pattern) for part in rel_parts for pattern in EXCLUDE_PATTERNS
        ):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(skill_path).as_posix())


def package_skills(catalog: Catalog, out_dir: Path) -> list[Path]:
    owned = not out_dir.exists() or (out_dir / DIST_MARKER).exists() or not any(out_dir.iterdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    if owned:
        (out_dir / DIST_MARKER).write_text("")
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
