"""Render the README's Skill catalog section."""

import re

from skillops.catalog import Catalog, CatalogError

CATALOG_START = "<!-- catalog:start -->"
CATALOG_END = "<!-- catalog:end -->"


def summarize(description: str, limit: int = 80) -> str:
    first_line = description.split("\n", 1)[0]
    match = re.match(r"(.*?(?:。|\.(?=\s)))", first_line)
    text = match.group(1) if match else first_line
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|")


def render_catalog_table(catalog: Catalog) -> str:
    sections = []
    for category in catalog.active_categories():
        rows = [
            f"### {category.title} (`{category.id}`)",
            "",
            "| Skill | Description | Web apps |",
            "|---|---|---|",
        ]
        for skill in catalog.skills_in(category.id):
            web = (
                f"[Download]({catalog.repo_url}/releases/download/latest/{skill.name}.zip)"
                if skill.web else "—"
            )
            rows.append(f"| `{skill.name}` | {summarize(skill.description)} | {web} |")
        sections.append("\n".join(rows))
    return "\n\n".join(sections) if sections else "_No skills yet._"


def replace_catalog_block(readme: str, table: str) -> str:
    start = readme.find(CATALOG_START)
    end = readme.find(CATALOG_END)
    if start == -1 or end == -1 or end < start:
        raise CatalogError(f"README.md is missing the {CATALOG_START} and {CATALOG_END} markers (or they are out of order)")
    head = readme[: start + len(CATALOG_START)]
    return f"{head}\n{table}\n{readme[end:]}"
