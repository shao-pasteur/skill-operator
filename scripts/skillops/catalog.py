"""Load categories.yaml and every SKILL.md under plugins/ into one Catalog."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from skillops.frontmatter import FrontmatterError, parse_frontmatter

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class Owner:
    name: str
    github: str


@dataclass(frozen=True)
class Category:
    id: str
    title: str
    description: str


@dataclass(frozen=True)
class Skill:
    category: str
    dir_name: str
    path: Path
    frontmatter: dict
    body: str

    @property
    def name(self) -> str:
        return str(self.frontmatter.get("name", self.dir_name))

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description", ""))

    @property
    def has_scripts(self) -> bool:
        return (self.path / "scripts").is_dir()

    @property
    def web(self) -> bool:
        metadata = self.frontmatter.get("metadata")
        if isinstance(metadata, dict) and "web" in metadata:
            return metadata["web"] == "true"
        return not self.has_scripts

    @property
    def rel_path(self) -> str:
        return f"plugins/{self.category}/skills/{self.dir_name}"


@dataclass(frozen=True)
class Catalog:
    root: Path
    marketplace: str
    owner: Owner
    categories: list[Category]
    skills: list[Skill]

    @property
    def repo_slug(self) -> str:
        return f"{self.owner.github}/{self.marketplace}"

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo_slug}"

    def skills_in(self, category_id: str) -> list[Skill]:
        return [s for s in self.skills if s.category == category_id]

    def active_categories(self) -> list[Category]:
        return [c for c in self.categories if self.skills_in(c.id)]


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"categories.yaml: {where} must be a non-empty string")
    return value


def _load_settings(root: Path) -> tuple[str, Owner, list[Category]]:
    path = root / "categories.yaml"
    if not path.is_file():
        raise CatalogError(f"categories.yaml not found in {root}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise CatalogError(f"categories.yaml is not valid YAML: {e}") from None
    if not isinstance(data, dict):
        raise CatalogError("categories.yaml must be a mapping at the top level")

    marketplace = _require_str(data.get("marketplace"), "marketplace")
    owner_data = data.get("owner")
    if not isinstance(owner_data, dict):
        raise CatalogError("categories.yaml: owner must have name and github")
    owner = Owner(
        name=_require_str(owner_data.get("name"), "owner.name"),
        github=_require_str(owner_data.get("github"), "owner.github"),
    )

    raw_categories = data.get("categories")
    if not isinstance(raw_categories, list):
        raise CatalogError("categories.yaml: categories must be a list")
    categories: list[Category] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_categories):
        if not isinstance(item, dict):
            raise CatalogError(f"categories.yaml: categories[{i}] must be a mapping")
        cid = _require_str(item.get("id"), f"categories[{i}].id")
        if not NAME_RE.match(cid):
            raise CatalogError(f"categories.yaml: category id '{cid}' may only use lowercase letters, digits and single hyphens")
        if cid in seen:
            raise CatalogError(f"categories.yaml: duplicate category id '{cid}'")
        seen.add(cid)
        categories.append(Category(
            id=cid,
            title=_require_str(item.get("title"), f"categories[{i}].title"),
            description=_require_str(item.get("description"), f"categories[{i}].description"),
        ))
    return marketplace, owner, categories


def _visible_dirs(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_dir() and not p.name.startswith("."))


def load_catalog(root: Path) -> Catalog:
    marketplace, owner, categories = _load_settings(root)
    known = {c.id for c in categories}
    for folder in _visible_dirs(root / "plugins"):
        if folder.name not in known:
            raise CatalogError(f"plugins/{folder.name} is not a category in categories.yaml")

    skills: list[Skill] = []
    for category in categories:
        for skill_dir in _visible_dirs(root / "plugins" / category.id / "skills"):
            rel = f"plugins/{category.id}/skills/{skill_dir.name}/SKILL.md"
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                raise CatalogError(f"{rel} is missing: every skill folder needs a SKILL.md")
            try:
                fm, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            except FrontmatterError as e:
                raise CatalogError(f"{rel}: {e}") from None
            skills.append(Skill(category.id, skill_dir.name, skill_dir, fm, body))
    return Catalog(root, marketplace, owner, categories, skills)
