"""Write the generated files to disk, or check that the committed copies are current."""

from collections.abc import Iterable

from skillops.catalog import Catalog, CatalogError
from skillops.manifests import MANIFEST_DIRS, render_manifests
from skillops.readme import render_catalog_table, replace_catalog_block
from skillops.validate import Issue


def generated_files(catalog: Catalog) -> dict[str, str]:
    readme_path = catalog.root / "README.md"
    if not readme_path.is_file():
        raise CatalogError("README.md not found")
    readme = replace_catalog_block(
        readme_path.read_text(encoding="utf-8"), render_catalog_table(catalog)
    )
    return {**render_manifests(catalog), "README.md": readme}


def stale_manifests(catalog: Catalog, expected: Iterable[str]) -> list[str]:
    expected = set(expected)
    found = []
    for manifest_dir in MANIFEST_DIRS:
        for path in catalog.root.glob(f"plugins/*/{manifest_dir}/plugin.json"):
            rel = path.relative_to(catalog.root).as_posix()
            if rel not in expected:
                found.append(rel)
    return sorted(found)


def write_generated(catalog: Catalog) -> list[str]:
    files = generated_files(catalog)
    stale = stale_manifests(catalog, files)
    changed = []
    for rel, content in files.items():
        path = catalog.root / rel
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed.append(rel)
    for rel in stale:
        path = catalog.root / rel
        path.unlink()
        if not any(path.parent.iterdir()):
            path.parent.rmdir()
        changed.append(rel)
    return changed


def check_generated(catalog: Catalog) -> list[Issue]:
    files = generated_files(catalog)
    issues = []
    for rel, content in files.items():
        path = catalog.root / rel
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            issues.append(Issue("error", rel, "generated file is outdated or missing; run make build"))
    for rel in stale_manifests(catalog, files):
        issues.append(Issue("error", rel, "this category has no skills left, so this generated file should be removed; run make build"))
    return issues
