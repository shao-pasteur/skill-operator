"""Check every skill against the Agent Skills spec and this repo's own rules."""

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from skillops.catalog import NAME_RE, Catalog, Skill

STANDARD_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata"})

_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_BARE_REF_RE = re.compile(r"(?<![A-Za-z0-9_/.:-])((?:scripts|references|assets)/[A-Za-z0-9_./-]+)")
_PERSONAL_PATH_RES = [
    re.compile(r"/Users/[^/\s<>\"'`]+/"),
    re.compile(r"/home/[^/\s<>\"'`]+/"),
    re.compile(r"(?i)C:\\Users\\[^\\\s<>]+\\"),
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
            issues.append(Issue("warning", where, f"frontmatter 欄位「{key}」不在 Agent Skills 標準中，部分平台會忽略它"))

    if "name" not in fm:
        issues.append(Issue("error", where, "缺少必填欄位 name"))
    else:
        name = fm["name"]
        if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
            issues.append(Issue("error", where, f"name「{name}」格式錯誤：只能用小寫英數字與單一連字號，最多 64 字元"))
        if name != skill.dir_name:
            issues.append(Issue("error", where, f"name「{name}」必須與資料夾名稱「{skill.dir_name}」相同"))

    description = fm.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(Issue("error", where, "缺少必填欄位 description"))
    else:
        if len(description) > 1024:
            issues.append(Issue("error", where, "description 超過 1024 字元"))
        if "TODO" in description:
            issues.append(Issue("error", where, "description 還是樣板內容（含 TODO），請改寫"))
        if len(description) < 50:
            issues.append(Issue("warning", where, "description 少於 50 字元，agent 可能不容易判斷何時使用"))

    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not isinstance(compat, str) or not 1 <= len(compat) <= 500:
            issues.append(Issue("error", where, "compatibility 必須是 1–500 字元的字串"))

    metadata = fm.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        issues.append(Issue("error", where, "metadata 必須是 key: value 形式的 mapping"))
        metadata = None
    for key, value in (metadata or {}).items():
        if not isinstance(value, str):
            issues.append(Issue("error", where, f'metadata.{key} 的值必須是字串，請寫成 "{_yaml_scalar(value)}"'))
        elif key == "web" and value not in ("true", "false"):
            issues.append(Issue("error", where, 'metadata.web 只能是 "true" 或 "false"'))
    if skill.has_scripts and "web" not in (metadata or {}):
        issues.append(Issue("error", where, '有 scripts/ 的 skill 必須在 metadata.web 註明網頁版能否使用（"true" 或 "false"）'))
    return issues


def _check_references(skill: Skill, where: str) -> list[Issue]:
    refs = [m.group(1) for m in _LINK_RE.finditer(skill.body)]
    refs += [m.group(1) for m in _BARE_REF_RE.finditer(skill.body)]
    issues: list[Issue] = []
    seen: set[str] = set()
    for ref in refs:
        if ":" in ref or ref.startswith("#"):
            continue
        ref = ref.split("#", 1)[0].rstrip(".,;:)")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        if not (skill.path / ref).exists():
            issues.append(Issue("error", where, f"引用的檔案不存在：{ref}"))
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
                issues.append(Issue("error", rel, f"Python 語法錯誤（{path.name} 第 {e.lineno} 行）：{e.msg}"))
        elif path.suffix == ".sh":
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            if result.returncode != 0:
                first = (result.stderr.strip().splitlines() or ["未知錯誤"])[0]
                issues.append(Issue("error", rel, f"shell 語法錯誤（{path.name}）：{first}"))
        for pattern in _PERSONAL_PATH_RES:
            for match in dict.fromkeys(m.group(0) for m in pattern.finditer(text)):
                issues.append(Issue("error", rel, f"含有個人路徑「{match}」，請改用環境變數或佔位符（例如 <你>）"))
        for match in dict.fromkeys(m.group(0) for m in _EMAIL_RE.finditer(text)):
            issues.append(Issue("warning", rel, f"含有 email「{match}」，公開 repo 請確認是否要保留"))
    return issues


def validate_catalog(catalog: Catalog) -> list[Issue]:
    name_counts = Counter(s.name for s in catalog.skills)
    issues: list[Issue] = []
    for skill in catalog.skills:
        where = f"{skill.rel_path}/SKILL.md"
        issues += _check_fields(skill, where)
        if name_counts[skill.name] > 1:
            others = [s.rel_path for s in catalog.skills if s.name == skill.name and s is not skill]
            issues.append(Issue("error", where, f"name「{skill.name}」與其他 skill 重複：{'、'.join(others)}"))
        line_count = len((skill.path / "SKILL.md").read_text(encoding="utf-8").splitlines())
        if line_count > 500:
            issues.append(Issue("warning", where, f"SKILL.md 有 {line_count} 行，超過建議的 500 行，可把細節移到 references/"))
        issues += _check_references(skill, where)
        issues += _check_files(catalog, skill)
    return issues
