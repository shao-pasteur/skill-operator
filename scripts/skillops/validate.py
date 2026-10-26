"""Check every skill against the Agent Skills spec and this repo's own rules."""

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from skillops.catalog import NAME_RE, Catalog, Skill

STANDARD_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata"})

_SKILL_DIRS = ("scripts/", "references/", "assets/")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_BARE_REF_RE = re.compile(r"(?<![A-Za-z0-9_/.:-])((?:scripts|references|assets)/[A-Za-z0-9_./-]+)")
_PERSONAL_PATH_RES = [
    re.compile(r"/Users/[^/\s<>\"'`]+"),
    re.compile(r"/home/[^/\s<>\"'`]+"),
    re.compile(r"(?i)C:\\{1,2}Users\\{1,2}[^\\\s<>\"']+"),
]
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass(frozen=True)
class Issue:
    level: str
    path: str
    message: str


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _check_fields(skill: Skill, where: str) -> list[Issue]:
    issues: list[Issue] = []
    fm = skill.frontmatter

    for key in fm:
        if key not in STANDARD_FIELDS:
            issues.append(Issue("warning", where, f"frontmatter field '{key}' is not part of the Agent Skills standard; some platforms ignore it"))

    if "name" not in fm:
        issues.append(Issue("error", where, "missing required field: name"))
    else:
        name = fm["name"]
        if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
            issues.append(Issue("error", where, f"name '{name}' is invalid: use lowercase letters, digits and single hyphens, at most 64 characters"))
        if name != skill.dir_name:
            issues.append(Issue("error", where, f"name '{name}' must match the folder name '{skill.dir_name}'"))

    description = fm.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(Issue("error", where, "missing required field: description"))
    else:
        if len(description) > 1024:
            issues.append(Issue("error", where, "description is longer than 1024 characters"))
        if "TODO" in description:
            issues.append(Issue("error", where, "description is still the template text (contains TODO); rewrite it"))
        if len(description) < 50:
            issues.append(Issue("warning", where, "description is shorter than 50 characters; agents may not know when to use the skill"))

    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not isinstance(compat, str) or not 1 <= len(compat) <= 500:
            issues.append(Issue("error", where, "compatibility must be a string of 1–500 characters"))

    metadata = fm.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(Issue("error", where, "metadata must be a key: value mapping"))
        metadata = None
    for key, value in (metadata or {}).items():
        if not isinstance(value, str):
            issues.append(Issue("error", where, f'metadata.{key} must be a string; write it as "{_yaml_scalar(value)}"'))
        elif key == "web" and value not in ("true", "false"):
            issues.append(Issue("error", where, 'metadata.web must be "true" or "false"'))
    if skill.has_scripts and "web" not in (metadata or {}):
        issues.append(Issue("error", where, 'skills with scripts/ must set metadata.web to "true" or "false" to say whether web apps can use them'))
    return issues


def _check_references(skill: Skill, where: str) -> list[Issue]:
    refs = [m.group(1) for m in _LINK_RE.finditer(skill.body)]
    refs += [m.group(1) for m in _BARE_REF_RE.finditer(skill.body)]
    issues: list[Issue] = []
    seen: set[str] = set()
    for ref in refs:
        if ":" in ref or ref.startswith("#"):
            continue
        ref = ref.split("#", 1)[0].rstrip(".,;:)").removeprefix("./")
        # Other relative links usually describe files the skill writes elsewhere.
        if not ref.startswith(_SKILL_DIRS) or ref in seen:
            continue
        seen.add(ref)
        if not (skill.path / ref).exists():
            issues.append(Issue("error", where, f"referenced file does not exist: {ref}"))
    return issues


def _skill_files(skill: Skill) -> list[Path]:
    return sorted(
        p for p in skill.path.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(skill.path).parts
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _check_files(catalog: Catalog, skill: Skill) -> list[Issue]:
    issues: list[Issue] = []
    for path in _skill_files(skill):
        text = _read_text(path)
        if text is None:
            continue
        rel = path.relative_to(catalog.root).as_posix()
        if path.suffix == ".py":
            try:
                compile(text, rel, "exec")
            except SyntaxError as e:
                issues.append(Issue("error", rel, f"Python syntax error in {path.name} line {e.lineno}: {e.msg}"))
        elif path.suffix == ".sh":
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            if result.returncode != 0:
                first = (result.stderr.strip().splitlines() or ["unknown error"])[0]
                issues.append(Issue("error", rel, f"shell syntax error in {path.name}: {first}"))
        for pattern in _PERSONAL_PATH_RES:
            for match in dict.fromkeys(m.group(0) for m in pattern.finditer(text)):
                issues.append(Issue("error", rel, f"contains a personal path '{match}'; use an environment variable or a placeholder such as <you>"))
        for match in dict.fromkeys(m.group(0) for m in _EMAIL_RE.finditer(text)):
            issues.append(Issue("warning", rel, f"contains an email address '{match}'; make sure it belongs in a public repo"))
    return issues


def validate_catalog(catalog: Catalog) -> list[Issue]:
    name_counts = Counter(s.name for s in catalog.skills)
    issues: list[Issue] = []
    for skill in catalog.skills:
        where = f"{skill.rel_path}/SKILL.md"
        issues += _check_fields(skill, where)
        if name_counts[skill.name] > 1:
            others = [s.rel_path for s in catalog.skills if s.name == skill.name and s is not skill]
            issues.append(Issue("error", where, f"name '{skill.name}' is also used by: {', '.join(others)}"))
        line_count = len((skill.path / "SKILL.md").read_text(encoding="utf-8").splitlines())
        if line_count > 500:
            issues.append(Issue("warning", where, f"SKILL.md has {line_count} lines, more than the recommended 500; move details into references/"))
        issues += _check_references(skill, where)
        issues += _check_files(catalog, skill)
    return issues
