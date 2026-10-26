from pathlib import Path

import pytest
import yaml

DEFAULT_CATEGORIES = [
    {"id": "dev", "title": "開發", "description": "開發工具"},
    {"id": "finance", "title": "財務", "description": "財務工具"},
]
DEFAULT_README = "# Test\n\n<!-- catalog:start -->\n<!-- catalog:end -->\n"


class RepoBuilder:
    def __init__(self, root: Path):
        self.root = root

    def write_categories(self, categories: list[dict] | None = None) -> None:
        data = {
            "marketplace": "test-market",
            "owner": {"name": "Tester", "github": "tester"},
            "categories": categories if categories is not None else DEFAULT_CATEGORIES,
        }
        (self.root / "categories.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def add_skill(
        self,
        category: str,
        name: str,
        *,
        frontmatter: dict | None = None,
        body: str = "# 指令\n",
        files: dict[str, str] | None = None,
        raw: str | None = None,
    ) -> Path:
        path = self.root / "plugins" / category / "skills" / name
        path.mkdir(parents=True, exist_ok=True)
        if raw is None:
            fm = frontmatter if frontmatter is not None else {
                "name": name,
                "description": "測試用 skill，" + "說明" * 30,
            }
            raw = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n" + body
        (path / "SKILL.md").write_text(raw, encoding="utf-8")
        for rel, content in (files or {}).items():
            target = path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return path

    def write_readme(self, text: str | None = None) -> None:
        (self.root / "README.md").write_text(
            DEFAULT_README if text is None else text, encoding="utf-8"
        )


@pytest.fixture
def repo(tmp_path: Path) -> RepoBuilder:
    builder = RepoBuilder(tmp_path / "repo")
    builder.root.mkdir()
    builder.write_categories()
    builder.write_readme()
    return builder
